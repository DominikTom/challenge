"""Orkiestracja całego pipeline'u (§5): adaptery -> matcher -> reconciler ->
tariff -> anomalie -> marża -> backtest. Wynik konsumują raporty i CLI.
"""

from __future__ import annotations

import re
from collections import Counter
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


_YYYYMM_RE = re.compile(r"(\d{4})-(\d{2})")
_MMYYYY_RE = re.compile(r"\b(\d{1,2})[./](\d{4})\b")


def _norm_period(value) -> str | None:
    """Znormalizuj różne zapisy do 'YYYY-MM' (np. 'FS/38/02/2026' -> '2026-02')."""
    if not value:
        return None
    s = str(value)
    m = _YYYYMM_RE.search(s)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    m = _MMYYYY_RE.search(s)  # MM/YYYY lub MM.YYYY (anchor na 4-cyfrowym roku)
    if m:
        mm = int(m.group(1))
        if 1 <= mm <= 12:
            return f"{m.group(2)}-{mm:02d}"
    return None


def _valid_period(period) -> bool:
    return bool(period) and bool(_YYYYMM_RE.fullmatch(str(period).strip()))


def detect_period(invoices: list[Invoice], deliveries: list[Delivery]) -> str | None:
    """Wykryj okres 'YYYY-MM' z faktur/zestawień (numery, daty, nr rozliczenia)."""
    from .util import period_of

    votes: Counter = Counter()
    for inv in invoices:
        for cand in (inv.period, inv.invoice_no, inv.settlement_no):
            p = _norm_period(cand)
            if p:
                votes[p] += 3
        p = period_of(inv.issue_date)
        if p:
            votes[p] += 2
    for d in deliveries:
        p = (period_of(d.delivery_date) or _norm_period(d.settlement_no)
             or _norm_period(d.invoice_no))
        if p:
            votes[p] += 1
    return votes.most_common(1)[0][0] if votes else None


def _resolve_period(period, invoices, deliveries) -> str | None:
    if _valid_period(period):
        return str(period).strip()
    return detect_period(invoices, deliveries)


def _stated_total(carrier: Carrier, adapter, spec_path: str) -> float | None:
    if hasattr(adapter, "stated_total"):
        try:
            return adapter.stated_total(spec_path)
        except Exception:
            return None
    return None


def run_pipeline(
    erp_path: str | Path | None,
    carrier_inputs: list[CarrierInput],
    period: str,
    cfg: Config | None = None,
    erp_source: str = "file",
) -> PipelineResult:
    """Uruchom pipeline. ``erp_source``: 'file' (Eksport.csv) lub 'supabase'.

    Dla 'supabase' najpierw parsujemy zestawienia przewoźników (żeby poznać
    rdzenie zamówień), a potem pobieramy z Supabase tylko te zamówienia +
    okno okresu (do nieobciążonych) — bez wgrywania całego Eksport.csv.
    """
    cfg = cfg or load_config()

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

    # --- okres: użyj podanego (YYYY-MM) albo wykryj z dokumentów -------------
    period = _resolve_period(period, invoices, all_deliveries)
    if not _valid_period(period):
        raise ValueError(
            "Nie udało się wykryć okresu z wgranych dokumentów — podaj go ręcznie "
            "w formacie RRRR-MM (np. 2026-02).")

    # --- źródło ERP: plik CSV albo Supabase (po rdzeniach z zestawień) -------
    if erp_source == "supabase":
        from .supabase_io import load_erp_from_supabase
        cores = [d.order_core for d in all_deliveries if d.order_core]
        erp = load_erp_from_supabase(cores, period, cfg)
    else:
        if erp_path is None:
            raise ValueError("erp_source='file' wymaga podania ścieżki do Eksport.csv")
        erp = load_erp(erp_path, cfg)

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
