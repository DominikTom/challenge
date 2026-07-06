"""Testy reconcilera (§9 twarde asserty) i backtestu matchera (§9 ≥98%)."""

import pytest

from transport_audit.core.backtest import carrier_from_manual_entry
from transport_audit.core.models import Carrier


def test_reconciliation_all_carriers(pipeline_result):
    by_carrier = {r.carrier: r for r in pipeline_result.recon_results}
    assert by_carrier["SPT"].actual_sum == pytest.approx(29225.96, abs=0.01)
    assert by_carrier["ZADBANO"].actual_sum == pytest.approx(98172.50, abs=0.01)
    assert by_carrier["DM_TRANS"].actual_sum == pytest.approx(5445.00, abs=0.01)
    assert all(r.within_tolerance for r in pipeline_result.recon_results)


def test_reconciliation_matches_invoice_net(pipeline_result):
    for r in pipeline_result.recon_results:
        assert r.expected_net is not None
        assert abs(r.delta) <= 0.01


def test_dm_settlement_pairing(pipeline_result):
    dm = next(r for r in pipeline_result.recon_results if r.carrier == "DM_TRANS")
    assert dm.settlement_no == "07/02/2026"
    assert dm.settlement_match


@pytest.mark.parametrize("entry,expected", [
    ("FS/38/02/2026 SPT", Carrier.SPT),
    ("307/02/2026/TR ZADBANO", Carrier.ZADBANO),
    ("FS/24/02/2026 D&M TRANS", Carrier.DM_TRANS),
    ("FS/133/06/2026 D&M TRANS", Carrier.DM_TRANS),
    ("", None),
])
def test_carrier_from_manual_entry(entry, expected):
    assert carrier_from_manual_entry(entry) == expected


def test_backtest_agreement_target(pipeline_result):
    bt = pipeline_result.backtest
    assert bt.total_with_manual > 0
    # cel §9: >= 98% zgodności przewoźnika na dopasowanych
    assert bt.agreement_rate >= 0.98


def test_backtest_precision_recall_present(pipeline_result):
    pr = pipeline_result.backtest.precision_recall()
    assert "SPT" in pr and "ZADBANO" in pr
    for stats in pr.values():
        assert 0.0 <= stats["precision"] <= 1.0
        assert 0.0 <= stats["recall"] <= 1.0
