"""Testy adaptera SPT: reconciliation 29 225,96, golden dubel 46046,
poziom usługi z `Typ zamówienia`, PODSUMOWANIE."""

import pytest

from transport_audit.adapters.spt import SptAdapter
from transport_audit.core.models import DeliveryStatus, ServiceLevel


def _parse(path):
    return SptAdapter("FS/38/02/2026", "2026-02").parse(path)


def test_reconciliation_29225(fixtures_dir):
    ds = _parse(fixtures_dir / "spt_spec.pdf")
    assert round(sum(d.total_cost_net for d in ds), 2) == pytest.approx(29225.96, abs=0.01)


def test_golden_double_46046(fixtures_dir):
    ds = _parse(fixtures_dir / "spt_spec.pdf")
    lines = sorted((d for d in ds if d.order_core == "46046"),
                   key=lambda d: d.total_cost_net)
    assert len(lines) == 2
    assert [round(d.total_cost_net, 2) for d in lines] == [259.60, 583.00]
    # Nieodebrane -> FAILED, Odebrane -> DELIVERED
    assert lines[0].status is DeliveryStatus.FAILED
    assert lines[1].status is DeliveryStatus.DELIVERED


def test_mybed_key_join(fixtures_dir):
    ds = _parse(fixtures_dir / "spt_spec.pdf")
    d = next(d for d in ds if d.order_ref_raw == "MYBED43503")
    assert d.order_core == "43503"


def test_service_level_from_order_type(fixtures_dir):
    ds = _parse(fixtures_dir / "spt_spec.pdf")
    d = next(d for d in ds if d.order_core == "43183")
    assert d.service_level is ServiceLevel.CARRY_IN
    d2 = next(d for d in ds if d.order_core == "43503")
    assert d2.service_level is ServiceLevel.DOOR


def test_stated_total_podsumowanie(fixtures_dir):
    adapter = SptAdapter("FS/38/02/2026", "2026-02")
    assert adapter.stated_total(fixtures_dir / "spt_spec.pdf") == pytest.approx(29225.96, abs=0.01)


def test_single_transport_component(fixtures_dir):
    ds = _parse(fixtures_dir / "spt_spec.pdf")
    # SPT: dokładnie 1 komponent = cała Cena transportu
    for d in ds:
        assert len(d.fees) == 1
        assert d.fees[0].amount_net == pytest.approx(d.total_cost_net, abs=0.01)
