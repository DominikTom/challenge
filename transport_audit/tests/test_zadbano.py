"""Testy adaptera Zadbano: reconciliation 98 172,50, zepsuty styles.xml,
golden 47559, 12 „niepowodzenie", podsumowanie."""

import pytest

from transport_audit.adapters.zadbano import ZadbanoAdapter, parse_summary
from transport_audit.core.models import DeliveryStatus, FeeType, ServiceLevel


def _parse(path):
    return ZadbanoAdapter("307/02/2026/TR", "2026-02",
                          settlement_no="307/02/2026/TR").parse(path)


def test_reconciliation_98172(fixtures_dir):
    ds = _parse(fixtures_dir / "zadbano_spec.xlsx")
    total = round(sum(d.total_cost_net for d in ds), 2)
    assert total == pytest.approx(98172.50, abs=0.01)


def test_openpyxl_fails_but_raw_reader_works(fixtures_dir):
    # openpyxl NIE otwiera pliku z zepsutym styles.xml...
    from openpyxl import load_workbook
    with pytest.raises(Exception):
        load_workbook(fixtures_dir / "zadbano_spec_broken.xlsx")
    # ...a nasz surowy czytnik XML radzi sobie i daje ten sam wynik
    ds = _parse(fixtures_dir / "zadbano_spec_broken.xlsx")
    assert round(sum(d.total_cost_net for d in ds), 2) == pytest.approx(98172.50, abs=0.01)


def test_golden_47559_components(fixtures_dir):
    ds = _parse(fixtures_dir / "zadbano_spec.xlsx")
    d = next(d for d in ds if d.order_core == "47559")
    assert d.total_cost_net == pytest.approx(568.52, abs=0.01)
    assert d.status is DeliveryStatus.DELIVERED
    assert d.amount_of(FeeType.TRANSPORT) == 480.0
    assert d.amount_of(FeeType.FUEL) == 48.0
    assert d.amount_of(FeeType.ROAD) == 25.0


def test_twelve_failed_sum(fixtures_dir):
    ds = _parse(fixtures_dir / "zadbano_spec.xlsx")
    failed = [d for d in ds if d.status is DeliveryStatus.FAILED]
    assert len(failed) == 12
    assert round(sum(d.total_cost_net for d in failed), 2) == pytest.approx(5251.37, abs=0.01)


def test_three_cancelled(fixtures_dir):
    ds = _parse(fixtures_dir / "zadbano_spec.xlsx")
    cancelled = [d for d in ds if d.status is DeliveryStatus.CANCELLED]
    assert len(cancelled) == 3


def test_komfort_maps_to_assembly(fixtures_dir):
    ds = _parse(fixtures_dir / "zadbano_spec.xlsx")
    d = next(d for d in ds if d.order_core == "46281")
    assert d.service_level is ServiceLevel.CARRY_IN_ASSEMBLY


def test_summary_balances(fixtures_dir):
    summ = parse_summary(fixtures_dir / "zadbano_spec.xlsx")
    assert summ["total"] == pytest.approx(98172.50, abs=0.01)
    assert round(sum(summ["categories"].values()), 2) == pytest.approx(summ["total"], abs=0.01)


def test_discount_is_negative(fixtures_dir):
    ds = _parse(fixtures_dir / "zadbano_spec.xlsx")
    disc = [d for d in ds if d.amount_of(FeeType.DISCOUNT) != 0]
    assert disc and all(d.amount_of(FeeType.DISCOUNT) < 0 for d in disc)
