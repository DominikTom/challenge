"""Testy adaptera D&M: dedup zdublowanych stron, reconciliation 5 445,00,
golden 47559, parametry paczek."""

import pytest

from transport_audit.adapters.dm_trans import DmTransAdapter
from transport_audit.core.models import DeliveryStatus, FeeType


def _parse(path):
    return DmTransAdapter("FS/24/02/2026", "2026-02",
                          settlement_no="07/02/2026").parse(path)


def test_dedup_and_reconciliation(fixtures_dir):
    ds = _parse(fixtures_dir / "dm_settlement.pdf")
    # PDF ma strony ×2 — po dedup 11 zleceń, Σ = 5 445,00
    assert len(ds) == 11
    assert round(sum(d.total_cost_net for d in ds), 2) == pytest.approx(5445.00, abs=0.01)


def test_golden_47559(fixtures_dir):
    ds = _parse(fixtures_dir / "dm_settlement.pdf")
    d = next(d for d in ds if d.order_core == "47559")
    assert d.total_cost_net == pytest.approx(455.00, abs=0.01)
    assert d.amount_of(FeeType.TRANSPORT) == pytest.approx(455.00, abs=0.01)
    assert d.status is DeliveryStatus.DELIVERED
    assert d.receiver_name and "Bronner" in d.receiver_name


def test_params_parsed(fixtures_dir):
    ds = _parse(fixtures_dir / "dm_settlement.pdf")
    d = next(d for d in ds if d.order_core == "47559")
    assert d.weight_kg == pytest.approx(45.0, abs=0.1)
    assert d.volume_m3 == pytest.approx(0.9, abs=0.01)
    assert d.qty == pytest.approx(2.0, abs=0.01)


def test_settlement_no_detected(fixtures_dir):
    ds = _parse(fixtures_dir / "dm_settlement.pdf")
    assert all(d.settlement_no == "07/02/2026" for d in ds)


def test_stated_total_footer(fixtures_dir):
    adapter = DmTransAdapter("FS/24/02/2026", "2026-02")
    assert adapter.stated_total(fixtures_dir / "dm_settlement.pdf") == pytest.approx(5445.00, abs=0.01)
