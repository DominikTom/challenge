"""Testy wczytania ERP: forward-fill, grupowanie, poziom usługi, rozmiary."""

from transport_audit.core.models import ServiceLevel


def test_forward_fill_and_grouping(erp):
    # jedno zamówienie per Numer mimo wielu wierszy-pozycji
    o = erp.by_number["Shoper47559-1"]
    assert o.core == "47559"
    assert o.number == "Shoper47559-1"


def test_service_level_from_items(erp):
    assert erp.by_number["Shoper47559-1"].service_level is ServiceLevel.DOOR
    assert erp.by_number["Shoper46281-1"].service_level is ServiceLevel.CARRY_IN_ASSEMBLY
    assert erp.by_number["Shoper43183-1"].service_level is ServiceLevel.CARRY_IN


def test_products_exclude_service_items(erp):
    o = erp.by_number["Shoper47559-1"]
    # pozycja-usługa „Wysyłka" nie może trafić do produktów
    assert "Wysyłka" not in o.products
    assert any("Auro" in p for p in o.products)


def test_size_extraction(erp):
    o = erp.by_number["Shoper47559-1"]
    assert "90x200" in o.sizes_cm


def test_core_index_prefix_collision(erp):
    # dwa zamówienia z tym samym rdzeniem, różne prefiksy
    cands = erp.get_by_core("12345")
    assert {c.number for c in cands} == {"Shoper12345-1", "Shopify12345-1"}
    prefixes = {c.prefix for c in cands}
    assert prefixes == {"Shoper", "Shopify"}


def test_existing_transport_invoice_read(erp):
    assert erp.by_number["Shoper47559-1"].existing_transport_invoice == "307/02/2026/TR ZADBANO"


def test_delivery_fee_and_total_parsed(erp):
    o = erp.by_number["Shoper47559-1"]
    assert o.delivery_fee_charged == 149.0
    assert o.order_total > 0
