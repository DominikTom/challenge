"""Testy matchera: złączenie po core, kolizja prefiksów, fuzzy, orphan, unbilled."""

from transport_audit.core.matcher import Matcher


def _all_deliveries(spt_deliveries, zadbano_deliveries, dm_deliveries):
    return list(spt_deliveries) + list(zadbano_deliveries) + list(dm_deliveries)


def test_core_join_and_counts(erp, spt_deliveries, zadbano_deliveries, dm_deliveries):
    deliveries = _all_deliveries(spt_deliveries, zadbano_deliveries, dm_deliveries)
    outcome = Matcher(erp).run(deliveries, "2026-02")
    matched = outcome.matched_deliveries()
    # prawie wszystko dopasowane; dokładnie 1 orphan (MYBED ZWROT 600794)
    assert len(outcome.orphans) == 1
    assert outcome.orphans[0].order_core == "600794"
    assert len(matched) == len(deliveries) - 1


def test_mybed_and_underscore_joins(erp, spt_deliveries, zadbano_deliveries, dm_deliveries):
    deliveries = _all_deliveries(spt_deliveries, zadbano_deliveries, dm_deliveries)
    outcome = Matcher(erp).run(deliveries, "2026-02")
    by_ref = {m.delivery.order_ref_raw: m for m in outcome.matches if m.is_matched}
    assert by_ref["MYBED43503"].erp_order.number == "Shoper43503-1"
    assert by_ref["Shoper47559-1_8801122"].erp_order.number == "Shoper47559-1"
    assert by_ref["47559"].erp_order.number == "Shoper47559-1"


def test_prefix_collision_resolved(erp, spt_deliveries):
    outcome = Matcher(erp).run(list(spt_deliveries), "2026-02")
    m = next(m for m in outcome.matches if m.delivery.order_ref_raw == "Shoper12345-1")
    assert m.erp_order.number == "Shoper12345-1"      # nie Shopify12345-1
    assert "core" in m.match_method


def test_fuzzy_fallback(erp, spt_deliveries):
    outcome = Matcher(erp).run(list(spt_deliveries), "2026-02")
    m = next(m for m in outcome.matches if m.delivery.order_ref_raw == "ODBIOR WLASNY BIELSKO")
    assert m.match_method == "fuzzy"
    assert m.erp_order.number == "Shopify77777-1"
    assert m.score >= 90


def test_unbilled_reported(erp, spt_deliveries, zadbano_deliveries, dm_deliveries):
    deliveries = _all_deliveries(spt_deliveries, zadbano_deliveries, dm_deliveries)
    outcome = Matcher(erp).run(deliveries, "2026-02")
    unbilled_numbers = {o.number for o in outcome.unbilled}
    # zamówienie z Wysyłką w okresie bez linii kosztu
    assert "Shoper49999-1" in unbilled_numbers
    # styczniowe zamówienie NIE może być w unbilled dla lutego
    assert "Shoper40000-1" not in unbilled_numbers
