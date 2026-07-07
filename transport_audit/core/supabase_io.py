"""Integracja z Supabase (panel.mybed.pl): import ERP + eksport wyników.

* SOURCE: `load_erp_from_supabase` czyta zamówienia ERP z `fact_orders` +
  `fact_order_items` przez RPC `audit_erp` (po rdzeniach z plików przewoźników
  ORAZ w oknie okresu — do wykrycia nieobciążonych). Dzięki temu nie trzeba
  wgrywać wielkiego `Eksport.csv`.
* SINK: `write_results` upsertuje `fact_delivery_costs` (klucz
  order_core+period+carrier) i dopisuje uzgodnienia do `reconciliation_log`.
  Bez poświadczeń zapisuje JSONL (fallback), nigdy nie wywala runu.

Klient PostgREST oparty o `urllib` (bez dodatkowych zależności w bundlu Vercela).
Poświadczenia z env: SUPABASE_URL + SUPABASE_KEY (lub *_SERVICE_KEY / *_ANON_KEY).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

from .config import Config, load_config
from .erp import ErpDataset, build_dataset
from .models import ErpOrder, FeeType, ServiceLevel, Severity, extract_core
from .util import extract_size_cm, normalize_postcode, parse_pl_number

RPC_ERP = "audit_erp"
TABLE_FACTS = "fact_delivery_costs"
TABLE_RECON = "reconciliation_log"


class SupabaseError(Exception):
    pass


class SupabaseClient:
    """Minimalny klient PostgREST (urllib)."""

    def __init__(self, url: str | None = None, key: str | None = None) -> None:
        self.url = (url or os.environ.get("SUPABASE_URL", "")).rstrip("/")
        self.key = (
            key
            or os.environ.get("SUPABASE_KEY")
            or os.environ.get("SUPABASE_SERVICE_KEY")
            or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
            or os.environ.get("SUPABASE_ANON_KEY")
            or ""
        )
        if not self.url or not self.key:
            raise SupabaseError("Brak SUPABASE_URL / SUPABASE_KEY w środowisku.")

    def _headers(self, extra: dict | None = None) -> dict:
        h = {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    def _request(self, method: str, path: str, *, body=None,
                 headers: dict | None = None, params: dict | None = None,
                 want_headers: bool = False):
        url = f"{self.url}/rest/v1/{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers=self._headers(headers))
        try:
            with urllib.request.urlopen(req, timeout=50) as resp:
                raw = resp.read().decode("utf-8")
                parsed = json.loads(raw) if raw.strip() else []
                return (parsed, dict(resp.headers)) if want_headers else parsed
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            raise SupabaseError(f"HTTP {e.code} {e.reason} na {path}: {detail}")
        except urllib.error.URLError as e:
            raise SupabaseError(f"Połączenie z Supabase nieudane: {e.reason}")

    def rpc(self, fn: str, payload: dict):
        return self._request("POST", f"rpc/{fn}", body=payload)

    def rpc_all(self, fn: str, payload: dict, page: int = 1000) -> list[dict]:
        """Wywołaj RPC z paginacją (odporność na PostgREST db-max-rows)."""
        out: list[dict] = []
        offset, total = 0, None
        while True:
            data, hdrs = self._request(
                "POST", f"rpc/{fn}", body=payload,
                headers={"Prefer": "count=exact"},
                params={"limit": page, "offset": offset}, want_headers=True)
            out.extend(data)
            got = len(data)
            offset += got
            cr = hdrs.get("Content-Range") or hdrs.get("content-range")
            if total is None and cr and "/" in cr:
                tail = cr.rsplit("/", 1)[-1]
                total = int(tail) if tail.isdigit() else None
            if got == 0:
                break
            if total is not None and offset >= total:
                break
            if total is None and got < page:
                break
        return out

    def upsert(self, table: str, rows: list[dict], on_conflict: str, batch: int = 500):
        for i in range(0, len(rows), batch):
            self._request(
                "POST", table, body=rows[i:i + batch],
                headers={"Prefer": "resolution=merge-duplicates,return=minimal"},
                params={"on_conflict": on_conflict})

    def insert(self, table: str, rows: list[dict], batch: int = 500):
        for i in range(0, len(rows), batch):
            self._request("POST", table, body=rows[i:i + batch],
                         headers={"Prefer": "return=minimal"})


# --------------------------------------------------------------------------- #
# SOURCE: ERP z Supabase
# --------------------------------------------------------------------------- #

def period_bounds(period: str) -> tuple[str, str]:
    """'YYYY-MM' -> ('YYYY-MM-01', pierwszy dzień kolejnego miesiąca)."""
    import re
    m0 = re.fullmatch(r"(\d{4})-(\d{2})", str(period).strip() if period else "")
    if not m0:
        raise SupabaseError(f"Zły okres '{period}' — oczekiwano formatu RRRR-MM.")
    y, m = int(m0.group(1)), int(m0.group(2))
    start = f"{y:04d}-{m:02d}-01"
    end = f"{y + 1:04d}-01-01" if m == 12 else f"{y:04d}-{m + 1:02d}-01"
    return start, end


def _service_level_from_items(items: list[dict], cfg: Config) -> ServiceLevel:
    """Wyprowadź poziom usługi z pozycji (item_type shipping/service + nazwa)."""
    mapped = []
    has_ship_or_service = False
    for it in items:
        itype = (it.get("item_type") or "").lower()
        if itype in ("shipping", "service"):
            has_ship_or_service = True
            lvl = cfg.service_level_for_item(it.get("product_name") or "")
            if lvl is not None:
                mapped.append(lvl)
    if mapped:
        return max(mapped, key=lambda l: l.rank)
    # nierozpoznana pozycja usługowa (np. niemieckie „Bestellung aufgeben")
    # -> baza DOOR, nie zakładamy wniesienia
    return ServiceLevel.DOOR if has_ship_or_service else ServiceLevel.UNKNOWN


def _erp_order_from_row(row: dict, cfg: Config) -> ErpOrder:
    items = row.get("items") or []
    products = [
        it.get("product_name") for it in items
        if (it.get("item_type") or "").lower() == "product" and it.get("product_name")
    ]
    sizes: list[str] = []
    for it in items:
        size = extract_size_cm(it.get("bed_size"))
        if size and size not in sizes:
            sizes.append(size)

    number = row.get("order_id") or ""
    tags = row.get("operational_tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.strip("{}").split(",") if t.strip()]
    zip_raw = row.get("delivery_zip")

    return ErpOrder(
        number=number,
        core=extract_core(number),
        order_date=row.get("order_date"),
        products=products,
        service_level=_service_level_from_items(items, cfg),
        sizes_cm=sizes,
        postcode=normalize_postcode(zip_raw) or (zip_raw or None),
        city=row.get("delivery_city"),
        delivery_fee_charged=parse_pl_number(row.get("shipping_cost_pln"), default=0.0) or 0.0,
        order_total=parse_pl_number(row.get("total_gross_pln"), default=0.0) or 0.0,
        status=row.get("status"),
        tags=list(tags),
        existing_transport_invoice=row.get("invoice_transport") or None,
        prefix="".join(c for c in number if c.isalpha()) or None,
        delivery_method=row.get("delivery_method"),
        receiver_name=row.get("customer_name"),
        street=None,
        row_index=None,
    )


def load_erp_from_supabase(
    cores: list[str],
    period: str,
    cfg: Config | None = None,
    client: SupabaseClient | None = None,
) -> ErpDataset:
    """Wczytaj ERP z Supabase: zamówienia po rdzeniach + w oknie okresu."""
    cfg = cfg or load_config()
    client = client or SupabaseClient()
    start, end = period_bounds(period)
    unique_cores = sorted({c for c in cores if c})
    rows = client.rpc_all(RPC_ERP, {
        "p_cores": unique_cores, "p_start": start, "p_end": end,
    })
    orders = [_erp_order_from_row(r, cfg) for r in rows]
    return build_dataset(orders)


# --------------------------------------------------------------------------- #
# SINK: wyniki do Supabase
# --------------------------------------------------------------------------- #

def _flags_by_number_and_core(result) -> tuple[dict, dict]:
    from .anomalies import R_CROSS, R_DOUBLE, R_FAILED
    tags_by_number: dict[str, list[str]] = defaultdict(list)
    recoverable_by_key: dict[tuple, float] = defaultdict(float)
    for f in result.audit.flags:
        tag = f"{f.rule}:{f.severity.value}"
        if f.order_number:
            tags_by_number[f.order_number].append(tag)
        if f.recoverable and f.rule in (R_CROSS, R_DOUBLE, R_FAILED) and f.order_core:
            recoverable_by_key[f.order_core] += f.recoverable
    return tags_by_number, recoverable_by_key


def build_fact_rows(result) -> list[dict]:
    """Rekordy do `fact_delivery_costs` per (order_core, period, carrier)."""
    tags_by_number, recoverable_by_core = _flags_by_number_and_core(result)
    grouped: dict[tuple, list] = defaultdict(list)
    for m in result.outcome.matches:
        d = m.delivery
        key = (d.order_core or f"ref:{d.order_ref_raw}", result.period, d.carrier.value)
        grouped[key].append(m)

    rows: list[dict] = []
    for (core, period, carrier), items in grouped.items():
        total = round(sum(i.delivery.total_cost_net for i in items), 2)
        transport = round(sum(i.delivery.amount_of(FeeType.TRANSPORT) for i in items), 2)
        erp = next((i.erp_order for i in items if i.erp_order), None)
        fees: dict[str, float] = defaultdict(float)
        for i in items:
            for f in i.delivery.fees:
                fees[f.type_code.value] += f.amount_net
        order_number = erp.number if erp else None
        flags = sorted(set(tags_by_number.get(order_number, []))) if order_number else []
        rows.append({
            "order_core": core,
            "period": period,
            "carrier": carrier,
            "order_number": order_number,
            "real_transport_cost_net": total,
            "transport_net": transport,
            "service_level": items[0].delivery.service_level.value,
            "status": items[0].delivery.status.value,
            "invoice_no": items[0].delivery.invoice_no,
            "match_method": items[0].match_method,
            "fee_breakdown": {k: round(v, 2) for k, v in fees.items()},
            "audit_flags": flags,
            "recoverable": round(recoverable_by_core.get(core, 0.0), 2) or None,
        })
    return rows


def build_recon_rows(result, run_day: str | None = None) -> list[dict]:
    """Rekordy do `reconciliation_log` per przebieg przewoźnika."""
    run_day = run_day or date.today().isoformat()
    rows = []
    for r in result.recon_results:
        pct = None
        if r.expected_net not in (None, 0) and r.delta is not None:
            pct = round(r.delta / r.expected_net * 100, 3)
        rows.append({
            "run_date": run_day,
            "source": f"transport_audit:{r.carrier}",
            "metric": f"sum_net_vs_invoice:{result.period}:{r.invoice_no}",
            "db_value": r.actual_sum,
            "api_value": r.expected_net,
            "difference": r.delta,
            "difference_pct": pct,
            "status": "ok" if r.within_tolerance else "mismatch",
        })
    return rows


def write_results(result, out_dir: str | Path | None = None,
                  client: SupabaseClient | None = None) -> dict:
    """Zapisz wyniki do Supabase (fact_delivery_costs + reconciliation_log).

    Bez poświadczeń: zapis JSONL do ``out_dir`` (fallback), status opisowy.
    """
    fact_rows = build_fact_rows(result)
    recon_rows = build_recon_rows(result)

    if client is None:
        try:
            client = SupabaseClient()
        except SupabaseError as exc:
            path = None
            if out_dir:
                out = Path(out_dir)
                out.mkdir(parents=True, exist_ok=True)
                path = out / "fact_delivery_costs.jsonl"
                path.write_text(
                    "\n".join(json.dumps(r, ensure_ascii=False) for r in fact_rows),
                    encoding="utf-8")
            return {"status": "fallback_file", "reason": str(exc),
                    "fact_rows": len(fact_rows), "recon_rows": len(recon_rows),
                    "file": str(path) if path else None}

    client.upsert(TABLE_FACTS, fact_rows, on_conflict="order_core,period,carrier")
    client.insert(TABLE_RECON, recon_rows)
    return {"status": "upserted", "table": TABLE_FACTS,
            "fact_rows": len(fact_rows), "recon_rows": len(recon_rows)}
