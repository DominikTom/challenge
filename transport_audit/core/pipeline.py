"""Orkiestracja całego pipeline'u (§5): adaptery -> matcher -> reconciler ->
tariff -> anomalie -> marża -> backtest. Wynik konsumują raporty i CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..adapters.dm_trans import DmTransAdapter
from ..adapters.invoice_pdf import parse_invoice
from ..adapters.spt import SptAdapter
from ..adapters.zadbano import ZadbanoAdapter, parse_summary as zadbano_summary
from .anomalies import AnomalyDetector, AuditResult
from .backtest import BacktestReport, run_backtest
from .config import Config, load_config
from .erp import ErpDataset, load_erp
from .margin import MarginReport, compute_margins
from .matcher import Matcher, MatchOutcome
from .models import Carrier, Delivery, Invoice
from .reconciler import CarrierRecon, ReconResult, aggregate, reconcile_run
from .tariff_model import TariffModel

ADAPTERS = {
    Carrier.SPT: SptAdapter,
    Carrier.ZADBANO: ZadbanoAdapter,
    Carrier.DM_TRANS: DmTransAdapter,
}


@dataclass
class CarrierInput:
    """Jeden przebieg `--carrier CARRIER:invoice=...,spec=...`."""

    carrier: Carrier
    spec_path: str
    invoice_path: str | None = None
    settlement_no: str | None = None


@dataclass
class PipelineResult:
    period: str
    erp: ErpDataset
    deliveries: list[Delivery]
    outcome: MatchOutcome
    invoices: list[Invoice]
    recon_results: list[ReconResult]
    recon_by_carrier: dict[str, CarrierRecon]
    tariff: TariffModel
    audit: AuditResult
    margins: MarginReport
    backtest: BacktestReport
    zadbano_summary: dict = field(default_factory=dict)


def _stated_total(carrier: Carrier, adapter, spec_path: str) -> float | None:
    if hasattr(adapter, "stated_total"):
        try:
            return adapter.stated_total(spec_path)
        except Exception:
            return None
    return None


def run_pipeline(
    erp_path: str | Path,
    carrier_inputs: list[CarrierInput],
    period: str,
    cfg: Config | None = None,
) -> PipelineResult:
    cfg = cfg or load_config()
    erp = load_erp(erp_path, cfg)

    all_deliveries: list[Delivery] = []
    invoices: list[Invoice] = []
    recon_results: list[ReconResult] = []
    zsummary: dict = {}

    for ci in carrier_inputs:
        invoice: Invoice | None = None
        if ci.invoice_path:
            invoice = parse_invoice(ci.invoice_path, ci.carrier)
            invoices.append(invoice)

        invoice_no = (invoice.invoice_no if invoice and invoice.invoice_no
                      else Path(ci.spec_path).stem)
        settlement_no = ci.settlement_no or (invoice.settlement_no if invoice else None)

        adapter_cls = ADAPTERS[ci.carrier]
        adapter = adapter_cls(invoice_no=invoice_no, period=period, cfg=cfg,
                              settlement_no=settlement_no)
        deliveries = adapter.parse(ci.spec_path)
        all_deliveries.extend(deliveries)

        if ci.carrier is Carrier.ZADBANO and not zsummary:
            zsummary = zadbano_summary(ci.spec_path)

        stated = _stated_total(ci.carrier, adapter, ci.spec_path)
        recon_results.append(
            reconcile_run(deliveries, invoice, stated_total=stated, cfg=cfg))

    outcome = Matcher(erp, cfg).run(all_deliveries, period)
    tariff = TariffModel.learn(outcome.matches, cfg)
    audit = AnomalyDetector(tariff, cfg).run(outcome, zsummary)
    margins = compute_margins(outcome)
    backtest = run_backtest(outcome.matches, cfg)
    recon_by_carrier = aggregate(recon_results)

    return PipelineResult(
        period=period, erp=erp, deliveries=all_deliveries, outcome=outcome,
        invoices=invoices, recon_results=recon_results,
        recon_by_carrier=recon_by_carrier, tariff=tariff, audit=audit,
        margins=margins, backtest=backtest, zadbano_summary=zsummary,
    )
