"""Uzgodnienie Σ kosztu zestawienia z kwotą netto faktury zbiorczej (§4, §9).

Tolerancja 0,01. Dla D&M faktura paruje się z rozliczeniem po numerze
rozliczenia + sumie (w miesiącu jest wiele faktur+rozliczeń), więc każdy
przebieg `--carrier` reconciliujemy osobno, a potem agregujemy per przewoźnik.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Config, load_config
from .models import Carrier, Delivery, Invoice


@dataclass
class ReconResult:
    carrier: str
    invoice_no: str
    settlement_no: str | None
    expected_net: float | None      # z faktury
    stated_total: float | None      # z stopki zestawienia (SPT/D&M)
    actual_sum: float               # Σ total_cost_net z linii
    n_deliveries: int
    delta: float | None             # actual_sum - expected_net
    within_tolerance: bool
    settlement_match: bool = True   # czy nr rozliczenia FV == nr rozliczenia zestawienia
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "carrier": self.carrier,
            "invoice_no": self.invoice_no,
            "settlement_no": self.settlement_no,
            "expected_net": _r(self.expected_net),
            "stated_total": _r(self.stated_total),
            "actual_sum": _r(self.actual_sum),
            "n_deliveries": self.n_deliveries,
            "delta": _r(self.delta),
            "within_tolerance": self.within_tolerance,
            "settlement_match": self.settlement_match,
            "notes": "; ".join(self.notes),
        }


def _r(x: float | None) -> float | None:
    return round(x, 2) if x is not None else None


def reconcile_run(
    deliveries: list[Delivery],
    invoice: Invoice | None,
    *,
    stated_total: float | None = None,
    cfg: Config | None = None,
) -> ReconResult:
    """Uzgodnij jeden przebieg (jedno zestawienie + jego faktura)."""
    cfg = cfg or load_config()
    tol = cfg.threshold("reconcile_tolerance")

    actual = round(sum(d.total_cost_net for d in deliveries), 2)
    expected = invoice.net if invoice else None
    carrier = deliveries[0].carrier.value if deliveries else (
        invoice.carrier.value if invoice else "?")
    invoice_no = invoice.invoice_no if invoice else (
        deliveries[0].invoice_no if deliveries else "")

    delta = round(actual - expected, 2) if expected is not None else None
    within = expected is not None and abs(delta) <= tol

    # numer rozliczenia zestawienia (spójny w liniach)
    spec_settlement = None
    for d in deliveries:
        if d.settlement_no:
            spec_settlement = d.settlement_no
            break

    settlement_match = True
    notes: list[str] = []
    if invoice and invoice.settlement_no and spec_settlement:
        settlement_match = invoice.settlement_no == spec_settlement
        if not settlement_match:
            notes.append(
                f"Nr rozliczenia FV ({invoice.settlement_no}) != zestawienie "
                f"({spec_settlement})")

    if stated_total is not None and expected is not None:
        if abs(stated_total - expected) > tol:
            notes.append(
                f"Stopka zestawienia ({stated_total}) != netto FV ({expected})")
    if expected is None:
        notes.append("Brak netto z faktury — uzgodnienie tylko względem stopki")

    return ReconResult(
        carrier=carrier,
        invoice_no=invoice_no,
        settlement_no=spec_settlement or (invoice.settlement_no if invoice else None),
        expected_net=expected,
        stated_total=stated_total,
        actual_sum=actual,
        n_deliveries=len(deliveries),
        delta=delta,
        within_tolerance=within,
        settlement_match=settlement_match,
        notes=notes,
    )


@dataclass
class CarrierRecon:
    carrier: str
    runs: list[ReconResult] = field(default_factory=list)

    @property
    def total_actual(self) -> float:
        return round(sum(r.actual_sum for r in self.runs), 2)

    @property
    def total_expected(self) -> float | None:
        vals = [r.expected_net for r in self.runs if r.expected_net is not None]
        return round(sum(vals), 2) if vals else None

    @property
    def all_ok(self) -> bool:
        return all(r.within_tolerance for r in self.runs)


def aggregate(results: list[ReconResult]) -> dict[str, CarrierRecon]:
    """Zgrupuj wyniki przebiegów per przewoźnik (agregacja miesięczna)."""
    out: dict[str, CarrierRecon] = {}
    for r in results:
        out.setdefault(r.carrier, CarrierRecon(carrier=r.carrier)).runs.append(r)
    return out
