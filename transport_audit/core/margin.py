"""Marża dostawy (§5.7): koszt pobrany od klienta (`Koszt dostawy`) vs realny
koszt przewoźnika. Oznacza wniesienie jako „przychód spoza źródła" — bo
przychód za wniesienie/montaż siedzi w pozycjach-usługach zamówienia, a nie w
`Koszt dostawy`, więc marża liczona wprost jest zaniżona dla CARRY_IN*.

# TODO(dom): „Decyzja 4" nie była dołączona do specyfikacji — przyjmuję, że
# przychód za wniesienie jest księgowany w pozycjach zamówienia i sygnalizuję
# to notatką zamiast doliczać (brak cen tych pozycji w modelu ErpOrder).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .matcher import MatchOutcome
from .models import FeeType, MatchResult, ServiceLevel


@dataclass
class MarginRecord:
    order_number: str | None
    order_core: str | None
    carrier: str
    fee_charged: float          # ERP `Koszt dostawy` (przychód od klienta)
    carrier_cost: float         # realny koszt przewoźnika (total_cost_net)
    margin: float               # fee_charged - carrier_cost
    service_level: str
    carry_in_revenue_offbook: bool  # czy przychód za wniesienie jest poza `Koszt dostawy`
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "order_number": self.order_number,
            "order_core": self.order_core,
            "carrier": self.carrier,
            "fee_charged": round(self.fee_charged, 2),
            "carrier_cost": round(self.carrier_cost, 2),
            "margin": round(self.margin, 2),
            "service_level": self.service_level,
            "carry_in_revenue_offbook": self.carry_in_revenue_offbook,
            "note": self.note,
        }


@dataclass
class MarginReport:
    records: list[MarginRecord] = field(default_factory=list)
    total_fee: float = 0.0
    total_cost: float = 0.0
    total_margin: float = 0.0
    loss_count: int = 0

    def to_summary(self) -> dict:
        return {
            "orders": len(self.records),
            "total_fee_charged": round(self.total_fee, 2),
            "total_carrier_cost": round(self.total_cost, 2),
            "total_margin": round(self.total_margin, 2),
            "loss_making_orders": self.loss_count,
        }


def compute_margins(outcome: MatchOutcome) -> MarginReport:
    """Policz marżę per dopasowane zamówienie + zagregowane podsumowanie."""
    report = MarginReport()
    for m in outcome.matches:
        if not m.is_matched:
            continue
        erp = m.erp_order
        fee = erp.delivery_fee_charged or 0.0
        cost = m.delivery.total_cost_net or 0.0
        margin = round(fee - cost, 2)
        carry_in = m.delivery.service_level in {
            ServiceLevel.CARRY_IN, ServiceLevel.CARRY_IN_ASSEMBLY
        } or erp.service_level in {ServiceLevel.CARRY_IN, ServiceLevel.CARRY_IN_ASSEMBLY}

        note = ""
        if carry_in:
            note = ("przychód za wniesienie/montaż w pozycjach zamówienia "
                    "(poza `Koszt dostawy`) — marża zaniżona")
        elif margin < 0:
            note = "strata na dostawie (koszt > opłata od klienta)"

        rec = MarginRecord(
            order_number=erp.number, order_core=m.delivery.order_core,
            carrier=m.delivery.carrier.value, fee_charged=fee, carrier_cost=cost,
            margin=margin, service_level=m.delivery.service_level.value,
            carry_in_revenue_offbook=carry_in, note=note)
        report.records.append(rec)
        report.total_fee += fee
        report.total_cost += cost
        report.total_margin += margin
        if margin < 0 and not carry_in:
            report.loss_count += 1
    report.total_fee = round(report.total_fee, 2)
    report.total_cost = round(report.total_cost, 2)
    report.total_margin = round(report.total_margin, 2)
    return report
