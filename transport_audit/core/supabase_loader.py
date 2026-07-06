"""Opcjonalny upsert do `fact_delivery_costs` (CFO tab w panel.mybed.pl).

Klucz: (order_core, period, carrier). Jeśli `supabase-py` lub poświadczenia są
niedostępne, zapisujemy plik `fact_delivery_costs.jsonl` do ręcznego importu —
nigdy nie wywalamy całego runu z powodu braku bazy.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path

from .models import FeeType
from .pipeline import PipelineResult

TABLE = "fact_delivery_costs"


def build_fact_rows(result: PipelineResult) -> list[dict]:
    """Zbuduj rekordy faktów per (order_core, carrier) w danym okresie."""
    grouped: dict[tuple, list] = defaultdict(list)
    for m in result.outcome.matches:
        d = m.delivery
        key = (d.order_core or f"ref:{d.order_ref_raw}", result.period, d.carrier.value)
        grouped[key].append(m)

    rows: list[dict] = []
    for (core, period, carrier), items in grouped.items():
        total = round(sum(i.delivery.total_cost_net for i in items), 2)
        erp = next((i.erp_order for i in items if i.erp_order), None)
        fees: dict[str, float] = defaultdict(float)
        for i in items:
            for f in i.delivery.fees:
                fees[f.type_code.value] += f.amount_net
        rows.append({
            "order_core": core,
            "period": period,
            "carrier": carrier,
            "order_number": erp.number if erp else None,
            "real_transport_cost_net": total,
            "transport_net": round(sum(i.delivery.amount_of(FeeType.TRANSPORT) for i in items), 2),
            "service_level": items[0].delivery.service_level.value,
            "status": items[0].delivery.status.value,
            "invoice_no": items[0].delivery.invoice_no,
            "match_method": items[0].match_method,
            "fee_breakdown": {k: round(v, 2) for k, v in fees.items()},
        })
    return rows


def load_to_supabase(result: PipelineResult, out_dir: str | Path) -> dict:
    """Upsert do Supabase; fallback do pliku JSONL. Zwraca status."""
    rows = build_fact_rows(result)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    fallback_path = out_dir / "fact_delivery_costs.jsonl"
    fallback_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY") or os.environ.get("SUPABASE_SERVICE_KEY")
    if not (url and key):
        return {"status": "fallback_file", "rows": len(rows),
                "file": str(fallback_path),
                "reason": "brak SUPABASE_URL / SUPABASE_KEY w środowisku"}

    try:
        from supabase import create_client  # type: ignore
    except ImportError:
        return {"status": "fallback_file", "rows": len(rows),
                "file": str(fallback_path), "reason": "brak pakietu supabase-py"}

    client = create_client(url, key)
    client.table(TABLE).upsert(
        rows, on_conflict="order_core,period,carrier").execute()
    return {"status": "upserted", "rows": len(rows), "table": TABLE}
