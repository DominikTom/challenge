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
from .models import (
    Carrier, Delivery, DeliveryStatus, FeeComponent, FeeType, Invoice, ServiceLevel,
)
from .reconciler import CarrierRecon, ReconResult, aggregate, reconcile_run
from .tariff_model import TariffModel

ADAPTERS = {
    Carrier.SPT: SptAdapter,
    Carrier.ZADBANO: ZadbanoAdapter,
    Carrier.DM_TRANS: DmTransAdapter,
}


@dataclass
class CarrierInput:
    """Wejście jednego przewoźnika: jedno lub WIELE zestawień + faktur.

    Wstecznie kompatybilne: ``spec_path`` / ``invoice_path`` (pojedyncze) albo
    ``spec_paths`` / ``invoice_paths`` (listy). Wiele zestawień u przewoźnika
    łączymy w jeden przebieg — sumujemy dostawy, a netto faktur sumujemy do
    jednego uzgodnienia (§4: Σ zestawień vs Σ faktur danego przewoźnika).
    """

    carrier: Carrier
    spec_path: str | None = None
    invoice_path: str | None = None
    settlement_no: str | None = None
    spec_paths: list[str] = field(default_factory=list)
    invoice_paths: list[str] = field(default_factory=list)

    def all_specs(self) -> list[str]:
        return list(self.spec_paths) if self.spec_paths else (
            [self.spec_path] if self.spec_path else [])

    def all_invoices(self) -> list[str]:
        return list(self.invoice_paths) if self.invoice_paths else (
            [self.invoice_path] if self.invoice_path else [])


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


def _combine_invoices(parsed: list[Invoice], carrier: Carrier) -> Invoice | None:
    """Złóż wiele faktur jednego przewoźnika w jedną (suma netto/VAT/brutto)."""
    parsed = [i for i in parsed if i]
    if not parsed:
        return None
    if len(parsed) == 1:
        return parsed[0]

    def _sum(attr):
        vals = [getattr(i, attr) for i in parsed if getattr(i, attr) is not None]
        return round(sum(vals), 2) if vals else None

    first = parsed[0]
    return Invoice(
        carrier=carrier,
        invoice_no=" + ".join(i.invoice_no for i in parsed if i.invoice_no),
        seller=first.seller, nip=first.nip, issue_date=first.issue_date,
        period=first.period, net=_sum("net"), vat=_sum("vat"), gross=_sum("gross"),
        payment_due=first.payment_due,
        settlement_no=next((i.settlement_no for i in parsed if i.settlement_no), None),
        source_path=None)


def _merge_zsummary(acc: dict, new: dict) -> dict:
    """Zsumuj kategorie dopłat Zadbano z wielu zestawień."""
    if not new:
        return acc
    if not acc:
        return {"categories": dict(new.get("categories", {})),
                "total": round(new.get("total") or 0.0, 2)}
    cats = dict(acc.get("categories", {}))
    for k, v in new.get("categories", {}).items():
        cats[k] = round(cats.get(k, 0.0) + v, 2)
    return {"categories": cats,
            "total": round((acc.get("total") or 0.0) + (new.get("total") or 0.0), 2)}


# --------------------------------------------------------------------------- #
# Parsowanie „na raty" (§ web): duże zestawienia przekraczają limit żądania
# Vercela (~4,5 MB), więc parsujemy je partiami po stronie serwera i zbieramy
# WYNIKI (małe) w kliencie, a audyt liczymy na złożonym, pełnym okresie.
# --------------------------------------------------------------------------- #

def _delivery_from_dict(d: dict) -> Delivery:
    return Delivery(
        carrier=Carrier(d["carrier"]), invoice_no=d["invoice_no"], period=d["period"],
        order_ref_raw=d["order_ref_raw"], order_core=d.get("order_core"),
        status=DeliveryStatus(d.get("status", "UNKNOWN")),
        service_level=ServiceLevel(d.get("service_level", "UNKNOWN")),
        waybill=d.get("waybill"), qty=d.get("qty"), weight_kg=d.get("weight_kg"),
        volume_m3=d.get("volume_m3"), total_cost_net=d.get("total_cost_net", 0.0),
        fees=[FeeComponent(FeeType(f["type_code"]), f["type_raw"], f["amount_net"])
              for f in d.get("fees", [])],
        receiver_name=d.get("receiver_name"), receiver_postcode=d.get("receiver_postcode"),
        receiver_city=d.get("receiver_city"), delivery_date=d.get("delivery_date"),
        settlement_no=d.get("settlement_no"), source_row=d.get("source_row"))


def _invoice_from_dict(i: dict) -> Invoice:
    return Invoice(
        carrier=Carrier(i["carrier"]), invoice_no=i["invoice_no"], seller=i.get("seller"),
        nip=i.get("nip"), issue_date=i.get("issue_date"), period=i.get("period"),
        net=i.get("net"), vat=i.get("vat"), gross=i.get("gross"),
        payment_due=i.get("payment_due"), settlement_no=i.get("settlement_no"),
        source_path=i.get("source_path"))


def _parse_one_carrier(ci: CarrierInput, period: str, cfg: Config,
                       with_stated_total: bool = True):
    """Sparsuj wszystkie zestawienia+faktury jednego przewoźnika (bez uzgadniania).

    ``with_stated_total=False`` pomija DRUGI przebieg po PDF (odczyt stopki
    „PODSUMOWANIE") — używane w web, gdzie liczy się czas (limit ~60 s), a
    stopka daje tylko dodatkową notę sanity, nie wpływa na sumę uzgodnienia.
    """
    specs = ci.all_specs()
    parsed_invoices = [inv for inv in (parse_invoice(p, ci.carrier)
                                       for p in ci.all_invoices()) if inv]
    combined = _combine_invoices(parsed_invoices, ci.carrier)
    invoice_no = (combined.invoice_no if combined and combined.invoice_no
                  else (Path(specs[0]).stem if specs else ci.carrier.value))
    settlement_no = ci.settlement_no or (combined.settlement_no if combined else None)
    adapter = ADAPTERS[ci.carrier](invoice_no=invoice_no, period=period, cfg=cfg,
                                   settlement_no=settlement_no)
    deliveries: list[Delivery] = []
    stated_sum, stated_seen, zs = 0.0, False, {}
    for sp in specs:
        deliveries.extend(adapter.parse(sp))
        if with_stated_total:
            st = _stated_total(ci.carrier, adapter, sp)
            if st is not None:
                stated_sum += st
                stated_seen = True
        if ci.carrier is Carrier.ZADBANO:
            zs = _merge_zsummary(zs, zadbano_summary(sp))
    stated = round(stated_sum, 2) if stated_seen else None
    return deliveries, parsed_invoices, combined, stated, zs


def _parse_carriers(carrier_inputs: list[CarrierInput], period: str, cfg: Config):
    """Parsuj + uzgodnij wszystkich przewoźników (ścieżka plikowa)."""
    all_deliveries: list[Delivery] = []
    invoices: list[Invoice] = []
    recon_results: list[ReconResult] = []
    zsummary: dict = {}
    for ci in carrier_inputs:
        dels, parsed_invs, combined, stated, zs = _parse_one_carrier(ci, period, cfg)
        all_deliveries.extend(dels)
        invoices.extend(parsed_invs)
        recon_results.append(reconcile_run(dels, combined, stated_total=stated, cfg=cfg))
        if zs:
            zsummary = _merge_zsummary(zsummary, zs)
    return all_deliveries, invoices, recon_results, zsummary


def parse_carrier_batch(carrier_inputs: list[CarrierInput], period: str,
                        cfg: Config | None = None) -> dict:
    """Sparsuj JEDNĄ partię plików -> serializowalny słownik per przewoźnik.

    Zwraca ``{"carriers": {CARRIER: {deliveries, invoices, stated_total}}, ...}``
    do zebrania w kliencie i połączenia w pełny okres (funkcja `_rebuild_from_parsed`).
    """
    cfg = cfg or load_config()
    carriers: dict[str, dict] = {}
    zsummary: dict = {}
    for ci in carrier_inputs:
        # web: pomijamy drugi przebieg po PDF (stopka), by zmieścić się w limicie czasu
        dels, parsed_invs, _combined, stated, zs = _parse_one_carrier(
            ci, period, cfg, with_stated_total=False)
        blk = carriers.setdefault(
            ci.carrier.value, {"deliveries": [], "invoices": [], "stated_total": None})
        blk["deliveries"].extend(d.to_dict() for d in dels)
        blk["invoices"].extend(inv.to_dict() for inv in parsed_invs)
        if stated is not None:
            blk["stated_total"] = round((blk["stated_total"] or 0.0) + stated, 2)
        if zs:
            zsummary = _merge_zsummary(zsummary, zs)
    return {"carriers": carriers, "zadbano_summary": zsummary}


def _rebuild_from_parsed(parsed: dict, cfg: Config):
    """Odtwórz dostawy/faktury/uzgodnienia ze zsumowanych partii (ścieżka web)."""
    all_deliveries: list[Delivery] = []
    invoices: list[Invoice] = []
    recon_results: list[ReconResult] = []
    for cval, blk in (parsed.get("carriers") or {}).items():
        carrier = Carrier(cval)
        dels = [_delivery_from_dict(d) for d in blk.get("deliveries", [])]
        invs = [_invoice_from_dict(i) for i in blk.get("invoices", [])]
        all_deliveries.extend(dels)
        invoices.extend(invs)
        combined = _combine_invoices(invs, carrier)
        recon_results.append(reconcile_run(
            dels, combined, stated_total=blk.get("stated_total"), cfg=cfg))
    return all_deliveries, invoices, recon_results, (parsed.get("zadbano_summary") or {})


def run_pipeline(
    erp_path: str | Path | None,
    carrier_inputs: list[CarrierInput],
    period: str,
    cfg: Config | None = None,
    erp_source: str = "file",
    parsed: dict | None = None,
) -> PipelineResult:
    """Uruchom pipeline. ``erp_source``: 'file' (Eksport.csv) lub 'supabase'.

    Dla 'supabase' najpierw parsujemy zestawienia przewoźników (żeby poznać
    rdzenie zamówień), a potem pobieramy z Supabase tylko te zamówienia +
    okno okresu (do nieobciążonych) — bez wgrywania całego Eksport.csv.

    ``parsed`` (opcjonalnie): gotowa, zsumowana treść zestawień/faktur z wielu
    partii (patrz `parse_carrier_batch`) — pomija parsowanie plików i liczy
    audyt na złożonym, pełnym okresie. Wtedy ``carrier_inputs`` jest ignorowane.
    """
    cfg = cfg or load_config()

    if parsed is not None:
        all_deliveries, invoices, recon_results, zsummary = _rebuild_from_parsed(parsed, cfg)
    else:
        all_deliveries, invoices, recon_results, zsummary = _parse_carriers(
            carrier_inputs, period, cfg)

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
