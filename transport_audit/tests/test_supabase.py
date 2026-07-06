"""Testy logiki integracji z Supabase (offline — bez sieci).

Mapowanie RPC->ErpOrder, wyprowadzenie poziomu usługi z item_type, budowa
rekordów do fact_delivery_costs / reconciliation_log, obsługa braku poświadczeń.
"""

import pytest

from transport_audit.core.config import load_config
from transport_audit.core.models import ServiceLevel
from transport_audit.core.supabase_io import (
    SupabaseClient,
    SupabaseError,
    _erp_order_from_row,
    _service_level_from_items,
    build_fact_rows,
    build_recon_rows,
    period_bounds,
)

CFG = load_config()


@pytest.mark.parametrize("items,expected", [
    ([{"item_type": "shipping", "product_name": "Wysyłka"}], ServiceLevel.DOOR),
    ([{"item_type": "service", "product_name": "Wniesienie zamówienia"}], ServiceLevel.CARRY_IN),
    ([{"item_type": "service", "product_name": "Wniesienie zamówienia z usługą montażu i sprzątania"}],
     ServiceLevel.CARRY_IN_ASSEMBLY),
    # niemiecki placeholder — nierozpoznany -> baza DOOR, nie zakładamy wniesienia
    ([{"item_type": "service", "product_name": "Bestellung aufgeben"}], ServiceLevel.DOOR),
    # najwyższy poziom wygrywa
    ([{"item_type": "shipping", "product_name": "Wysyłka"},
      {"item_type": "service", "product_name": "Wniesienie zamówienia z usługą montażu i sprzątania"}],
     ServiceLevel.CARRY_IN_ASSEMBLY),
    ([{"item_type": "product", "product_name": "Łóżko"}], ServiceLevel.UNKNOWN),
])
def test_service_level_from_items(items, expected):
    assert _service_level_from_items(items, CFG) is expected


def test_erp_order_from_row():
    row = {
        "order_id": "Shoper46281-1_x", "order_date": "2026-02-01T10:00:00+00:00",
        "delivery_zip": "80-001", "delivery_city": "Gdańsk", "status": "zrealizowane",
        "shipping_cost_pln": 149.0, "total_gross_pln": 2499.0,
        "invoice_transport": "307/02/2026/TR ZADBANO", "customer_name": "Jan Kowalski",
        "operational_tags": ["vip"], "delivery_method": "SPT Logistics",
        "items": [
            {"item_type": "product", "product_name": "Łóżko Lea", "bed_size": "160cm x 200cm", "quantity": 1},
            {"item_type": "service", "product_name": "Wniesienie zamówienia", "bed_size": None, "quantity": 1},
        ],
    }
    o = _erp_order_from_row(row, CFG)
    assert o.number == "Shoper46281-1_x" and o.core == "46281"
    assert o.service_level is ServiceLevel.CARRY_IN
    assert o.sizes_cm == ["160x200"]
    assert o.products == ["Łóżko Lea"]
    assert o.existing_transport_invoice == "307/02/2026/TR ZADBANO"
    assert o.postcode == "80-001"


def test_period_bounds():
    assert period_bounds("2026-02") == ("2026-02-01", "2026-03-01")
    assert period_bounds("2026-12") == ("2026-12-01", "2027-01-01")


def test_build_fact_rows_from_pipeline(pipeline_result):
    rows = build_fact_rows(pipeline_result)
    keys = [(r["order_core"], r["period"], r["carrier"]) for r in rows]
    assert len(keys) == len(set(keys))
    cc = next(r for r in rows if r["order_core"] == "47559")
    assert "CROSS_CARRIER:FLAG" in cc["audit_flags"]
    assert cc["recoverable"] == pytest.approx(455.0, abs=0.01)
    assert isinstance(cc["fee_breakdown"], dict)


def test_build_recon_rows(pipeline_result):
    rows = build_recon_rows(pipeline_result, run_day="2026-02-28")
    assert {r["source"] for r in rows} >= {"transport_audit:SPT", "transport_audit:ZADBANO"}
    for r in rows:
        assert r["status"] in ("ok", "mismatch")
        assert r["run_date"] == "2026-02-28"


def test_client_requires_creds(monkeypatch):
    for k in ("SUPABASE_URL", "SUPABASE_KEY", "SUPABASE_SERVICE_KEY",
              "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_ANON_KEY"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(SupabaseError):
        SupabaseClient()
