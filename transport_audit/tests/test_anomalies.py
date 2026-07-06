"""Testy reguł audytu (§6) — golden cases §9."""

import pytest

from transport_audit.core.anomalies import (
    AnomalyDetector,
    R_CROSS,
    R_DOUBLE,
    R_FAILED,
    R_SERVICE,
    R_TARIFF,
    R_VOLUME,
)
from transport_audit.core.matcher import Matcher
from transport_audit.core.models import Severity
from transport_audit.core.tariff_model import TariffModel


@pytest.fixture(scope="module")
def audit(pipeline_result):
    return pipeline_result.audit


def test_cross_carrier_47559(audit):
    cc = [f for f in audit.by_rule(R_CROSS) if f.order_core == "47559"]
    assert len(cc) == 1
    f = cc[0]
    assert f.severity is Severity.FLAG
    assert f.amount == pytest.approx(1023.52, abs=0.01)   # 568.52 + 455.00
    assert f.recoverable == pytest.approx(455.00, abs=0.01)  # min z dwóch


def test_intra_double_46046(audit):
    dd = [f for f in audit.by_rule(R_DOUBLE) if f.order_core == "46046"]
    assert len(dd) == 1
    assert dd[0].severity is Severity.FLAG
    assert dd[0].amount == pytest.approx(842.60, abs=0.01)
    assert dd[0].recoverable == pytest.approx(259.60, abs=0.01)  # obciążenie za nieudane


def test_failed_charged_zadbano(audit):
    failed = audit.by_rule(R_FAILED)
    zad = [f for f in failed if f.carrier == "ZADBANO"]
    assert len(zad) == 15               # 12 niepowodzenie + 3 anulowane
    assert round(sum(f.amount for f in zad), 2) == pytest.approx(6001.37, abs=0.01)
    # golden: SPT Nieodebrane 46046 też jest „charged for failed"
    assert any(f.carrier == "SPT" and f.order_core == "46046" for f in failed)


def test_service_mismatch_flags(audit):
    flags = {f.order_core for f in audit.by_rule(R_SERVICE) if f.severity is Severity.FLAG}
    assert "46600" in flags     # Zadbano Komfort, ERP DOOR
    assert "43900" in flags     # SPT z wniesieniem, ERP DOOR


def test_above_tariff_overpay(audit):
    at = [f for f in audit.by_rule(R_TARIFF)
          if f.order_core == "48120" and f.severity is Severity.FLAG]
    assert at, "brak flagi above-tariff dla przepłaty 48120"
    assert at[0].amount == pytest.approx(600.00, abs=0.01)
    assert at[0].expected is not None and at[0].amount > at[0].expected * 1.20


def test_volume_recheck_flag(audit):
    vr = [f for f in audit.by_rule(R_VOLUME) if f.order_core == "48021"]
    assert vr, "brak weryfikacji objętości dla 48021"


def test_split_shipment_is_info_not_flag():
    """Dwa DELIVERED tego samego core -> INFO split, nie FLAG."""
    from transport_audit.core.models import (
        Carrier, Delivery, DeliveryStatus, FeeComponent, FeeType, ServiceLevel)
    from transport_audit.core.matcher import MatchOutcome, MatchResult

    def mk(amount, vol):
        d = Delivery(carrier=Carrier.SPT, invoice_no="X", period="2026-02",
                     order_ref_raw="Shoper55555-1", order_core="55555",
                     status=DeliveryStatus.DELIVERED, service_level=ServiceLevel.DOOR,
                     volume_m3=vol, total_cost_net=amount,
                     fees=[FeeComponent(FeeType.TRANSPORT, "t", amount)])
        return MatchResult(d, None, "core")

    outcome = MatchOutcome(matches=[mk(200.0, 0.4), mk(210.0, 0.4)])
    audit = AnomalyDetector().run(outcome)
    dd = audit.by_rule(R_DOUBLE)
    assert len(dd) == 1 and dd[0].severity is Severity.INFO


def test_identical_amounts_flag():
    """Dwie identyczne kwoty tego samego core -> FLAG double charge."""
    from transport_audit.core.models import (
        Carrier, Delivery, DeliveryStatus, FeeComponent, FeeType, ServiceLevel)
    from transport_audit.core.matcher import MatchOutcome, MatchResult

    def mk(amount):
        d = Delivery(carrier=Carrier.SPT, invoice_no="X", period="2026-02",
                     order_ref_raw="Shoper66666-1", order_core="66666",
                     status=DeliveryStatus.DELIVERED, service_level=ServiceLevel.DOOR,
                     total_cost_net=amount,
                     fees=[FeeComponent(FeeType.TRANSPORT, "t", amount)])
        return MatchResult(d, None, "core")

    outcome = MatchOutcome(matches=[mk(300.0), mk(300.0)])
    audit = AnomalyDetector().run(outcome)
    dd = audit.by_rule(R_DOUBLE)
    assert len(dd) == 1 and dd[0].severity is Severity.FLAG
    assert dd[0].recoverable == pytest.approx(300.0, abs=0.01)
