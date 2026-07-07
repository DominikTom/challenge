"""Testy oficjalnych cenników + reguły „przepłata vs cennik"."""

import pytest

from transport_audit.core.anomalies import AnomalyDetector, R_TARIFF
from transport_audit.core.matcher import MatchOutcome, MatchResult
from transport_audit.core.models import (
    Carrier, Delivery, DeliveryStatus, ErpOrder, FeeComponent, FeeType,
    ServiceLevel, Severity,
)
from transport_audit.core.tariff_official import (
    expected_transport, infer_market, lookup_spt, lookup_zadbano, zadbano_carry_in,
)


def test_spt_pl_lookup_matches_image():
    assert lookup_spt("PL", 0.5, ServiceLevel.DOOR) == (126, "PLN")       # próg 0.5-0.59
    assert lookup_spt("PL", 0.5, ServiceLevel.CARRY_IN) == (230, "PLN")
    assert lookup_spt("PL", 8.5, ServiceLevel.DOOR) is None               # > tabela


def test_spt_de_lookup_eur():
    assert lookup_spt("DE", 1.5, ServiceLevel.CARRY_IN_ASSEMBLY) == (157.5, "EUR")
    assert lookup_spt("DE", 0.1, ServiceLevel.DOOR) == (49.35, "EUR")     # próg 0-0.29


def test_zadbano_base_ignores_carry_in():
    # macierz zwraca BAZĘ transportu (wniesienie to osobny komponent)
    assert lookup_zadbano(0.9, 60, ServiceLevel.DOOR) == (187.34, "PLN")
    assert lookup_zadbano(0.9, 60, ServiceLevel.CARRY_IN) == (187.34, "PLN")  # bez carry
    assert zadbano_carry_in(60) == 45.53
    assert lookup_zadbano(3.5, 60, ServiceLevel.DOOR) is None             # > 3 m³


@pytest.mark.parametrize("pc,cur,exp", [
    ("30-001", None, "PL"), (None, "EUR", "DE"), (None, "PLN", "PL"),
    ("48282", None, "PL"),  # 5-cyfrowy bez myślnika -> domyślnie PL
])
def test_infer_market(pc, cur, exp):
    assert infer_market(pc, cur) == exp


def _zadbano_delivery(transport, vol, weight, service=ServiceLevel.DOOR):
    d = Delivery(carrier=Carrier.ZADBANO, invoice_no="307/02/2026/TR", period="2026-02",
                 order_ref_raw="Shoper70000-1", order_core="70000",
                 status=DeliveryStatus.DELIVERED, service_level=service,
                 volume_m3=vol, weight_kg=weight, total_cost_net=transport,
                 fees=[FeeComponent(FeeType.TRANSPORT, "Transport", transport)])
    erp = ErpOrder(number="Shoper70000-1", core="70000", order_date="2026-02-01",
                   products=[], service_level=service, sizes_cm=[], postcode="30-001",
                   city="Kraków", delivery_fee_charged=0.0, order_total=0.0,
                   status="zrealizowane", tags=[], existing_transport_invoice=None)
    return MatchResult(d, erp, "core")


def test_official_overpay_flag():
    # baza Zadbano dla 0.9 m³ / 60 kg = 187.34; koszt 250 > 187.34×1.05 -> FLAG
    outcome = MatchOutcome(matches=[_zadbano_delivery(250.0, 0.9, 60)])
    audit = AnomalyDetector(tariff=None).run(outcome)
    flags = [f for f in audit.by_rule(R_TARIFF) if f.severity is Severity.FLAG]
    assert len(flags) == 1
    assert "official tariff" in flags[0].message
    assert flags[0].expected == pytest.approx(187.34, abs=0.01)
    assert flags[0].amount == pytest.approx(250.0, abs=0.01)


def test_official_within_tariff_no_flag():
    # koszt 190 < 187.34×1.05=196.7 -> brak flagi (w normie), mediana nie dubluje
    outcome = MatchOutcome(matches=[_zadbano_delivery(190.0, 0.9, 60)])
    audit = AnomalyDetector(tariff=None).run(outcome)
    assert not [f for f in audit.by_rule(R_TARIFF) if f.severity is Severity.FLAG]
