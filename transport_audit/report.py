"""Generowanie wyjść (§7): enriched_orders.csv, audit_report.xlsx,
reference_tariff.json.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import pandas as pd

from .core.anomalies import (
    AuditResult,
    R_CROSS,
    R_DOUBLE,
    R_FAILED,
    R_OPS,
    R_SERVICE,
    R_SURCHARGE,
    R_TARIFF,
    R_VOLUME,
)
from .core.backtest import BacktestReport, carrier_from_manual_entry
from .core.config import Config, load_config
from .core.matcher import MatchOutcome
from .core.models import MatchResult, Severity
from .core.pipeline import PipelineResult


# --------------------------------------------------------------------------- #
# Indeksy pomocnicze
# --------------------------------------------------------------------------- #

def _matches_by_order(outcome: MatchOutcome) -> dict[str, list[MatchResult]]:
    by_order: dict[str, list[MatchResult]] = defaultdict(list)
    for m in outcome.matches:
        if m.is_matched:
            by_order[m.erp_order.number].append(m)
    return by_order


def _flags_by_order(audit: AuditResult, outcome: MatchOutcome) -> dict[str, list[str]]:
    """Mapuj numer zamówienia ERP -> lista kodów reguł (do kolumny audit_flags)."""
    core_to_numbers: dict[str, set[str]] = defaultdict(set)
    for m in outcome.matches:
        if m.is_matched and m.delivery.order_core:
            core_to_numbers[m.delivery.order_core].add(m.erp_order.number)

    out: dict[str, list[str]] = defaultdict(list)
    for f in audit.flags:
        numbers: set[str] = set()
        if f.order_number:
            numbers.add(f.order_number)
        elif f.order_core and f.order_core in core_to_numbers:
            numbers.update(core_to_numbers[f.order_core])
        tag = f"{f.rule}:{f.severity.value}"
        for n in numbers:
            if tag not in out[n]:
                out[n].append(tag)
    return out


# --------------------------------------------------------------------------- #
# 1) enriched_orders.csv
# --------------------------------------------------------------------------- #

def build_enriched_rows(result: PipelineResult, cfg: Config | None = None) -> list[dict]:
    cfg = cfg or load_config()
    by_order = _matches_by_order(result.outcome)
    flags_map = _flags_by_order(result.audit, result.outcome)
    unbilled_numbers = {o.number for o in result.outcome.unbilled}

    rows: list[dict] = []
    for order in result.erp.orders:
        matches = by_order.get(order.number, [])
        real_cost = round(sum(m.delivery.total_cost_net for m in matches), 2) if matches else None

        carriers, methods, statuses, service_levels = [], [], [], []
        breakdown = []
        invoice_labels = []
        for m in matches:
            d = m.delivery
            if d.carrier.value not in carriers:
                carriers.append(d.carrier.value)
            methods.append(m.match_method)
            statuses.append(d.status.value)
            service_levels.append(d.service_level.value)
            breakdown.append({
                "carrier": d.carrier.value,
                "invoice_no": d.invoice_no,
                "total_net": round(d.total_cost_net, 2),
                "fees": [f.to_dict() for f in d.fees],
            })
            label = f"{d.invoice_no} {cfg.carrier_label(d.carrier.value)}"
            if label not in invoice_labels:
                invoice_labels.append(label)

        existing = order.existing_transport_invoice
        auto_value = " | ".join(invoice_labels)
        # nadpisz tylko puste; jeśli istniał ręczny wpis — zostaw
        filled = existing if existing else auto_value

        validation = ""
        if existing and carriers:
            manual_carrier = carrier_from_manual_entry(existing, cfg)
            auto_carriers = set(carriers)
            if manual_carrier is None:
                validation = "ręczny wpis nieczytelny"
            elif manual_carrier.value not in auto_carriers:
                validation = f"MISMATCH ręczny={manual_carrier.value} auto={','.join(sorted(auto_carriers))}"
            else:
                validation = "OK"

        order_flags = list(flags_map.get(order.number, []))
        if order.number in unbilled_numbers:
            order_flags.append("UNBILLED:INFO")

        rows.append({
            "Numer": order.number,
            "Data zamówienia": order.order_date,
            "Kod pocztowy": order.postcode,
            "Miasto": order.city,
            "Klient/Nazwa": order.receiver_name,
            "Suma": order.order_total,
            "Koszt dostawy": order.delivery_fee_charged,
            "Status": order.status,
            "service_level_erp": order.service_level.value,
            "Faktura transportowa": filled,
            "real_transport_cost_net": real_cost,
            "carrier": ",".join(carriers),
            "service_level_matched": ",".join(dict.fromkeys(service_levels)),
            "status_carrier": ",".join(dict.fromkeys(statuses)),
            "cost_breakdown_json": json.dumps(breakdown, ensure_ascii=False) if breakdown else "",
            "match_method": ",".join(dict.fromkeys(methods)),
            "audit_flags": "; ".join(order_flags),
            "existing_transport_invoice": existing or "",
            "transport_invoice_validation": validation,
        })
    return rows


def write_enriched_orders(result: PipelineResult, path: str | Path,
                          cfg: Config | None = None) -> None:
    rows = build_enriched_rows(result, cfg)
    df = pd.DataFrame(rows)
    df.to_csv(path, index=False, encoding="utf-8-sig", sep=";")


# --------------------------------------------------------------------------- #
# 2) audit_report.xlsx
# --------------------------------------------------------------------------- #

def _flags_df(audit: AuditResult, rule: str, columns: list[str]) -> pd.DataFrame:
    rows = []
    for f in audit.by_rule(rule):
        d = f.to_dict()
        rows.append({c: d.get(c) for c in columns})
    return pd.DataFrame(rows, columns=columns)


def write_audit_report(result: PipelineResult, path: str | Path,
                       cfg: Config | None = None) -> None:
    cfg = cfg or load_config()
    audit = result.audit
    outcome = result.outcome

    base_cols = ["order_core", "order_number", "carrier", "severity", "message",
                 "amount", "expected", "delta", "recoverable", "evidence"]

    # Cross_carrier (na górze) — posortowane po recoverable malejąco
    cross = _flags_df(audit, R_CROSS,
                      ["order_core", "order_number", "amount", "recoverable", "evidence"])
    if not cross.empty:
        cross = cross.sort_values("recoverable", ascending=False)

    duble = _flags_df(audit, R_DOUBLE, base_cols)
    przeplaty = _flags_df(audit, R_TARIFF, base_cols)
    nieudane = _flags_df(audit, R_FAILED, base_cols)
    service = _flags_df(audit, R_SERVICE, base_cols)
    surcharge = _flags_df(audit, R_SURCHARGE, base_cols)
    ops = _flags_df(audit, R_OPS, base_cols)
    volume = _flags_df(audit, R_VOLUME, base_cols)

    orphans = pd.DataFrame([{
        "order_ref_raw": o.order_ref_raw, "order_core": o.order_core,
        "carrier": o.carrier.value, "total_cost_net": round(o.total_cost_net, 2),
        "receiver": o.receiver_name, "postcode": o.receiver_postcode,
    } for o in outcome.orphans])

    unbilled = pd.DataFrame([{
        "number": o.number, "core": o.core, "service_level": o.service_level.value,
        "city": o.city, "postcode": o.postcode, "order_date": o.order_date,
        "delivery_fee_charged": o.delivery_fee_charged,
    } for o in outcome.unbilled])

    # Podsumowanie per przewoźnik
    flags_by_carrier: dict[str, int] = defaultdict(int)
    for f in audit.flags:
        if f.severity is Severity.FLAG:
            flags_by_carrier[f.carrier] += 1
    summary_rows = []
    for carrier, rec in result.recon_by_carrier.items():
        summary_rows.append({
            "carrier": carrier,
            "Σ_koszt_netto": rec.total_actual,
            "netto_faktury": rec.total_expected,
            "delta": (round(rec.total_actual - rec.total_expected, 2)
                      if rec.total_expected is not None else None),
            "uzgodnione": rec.all_ok,
            "n_przebiegow": len(rec.runs),
            "n_FLAG": flags_by_carrier.get(carrier, 0),
        })
    summary = pd.DataFrame(summary_rows)

    # Reconciliation szczegółowo (per przebieg)
    recon = pd.DataFrame([r.to_dict() for r in result.recon_results])

    # Walidacja vs ręczne
    validation_rows = []
    for row in build_enriched_rows(result, cfg):
        v = row["transport_invoice_validation"]
        if v and v != "OK":
            validation_rows.append({
                "Numer": row["Numer"],
                "existing": row["existing_transport_invoice"],
                "auto_carrier": row["carrier"],
                "auto_faktura": row["Faktura transportowa"],
                "problem": v,
            })
    validation = pd.DataFrame(validation_rows)

    # Marża (najgorsze + wszystkie carry-in offbook)
    margin_rows = [r.to_dict() for r in result.margins.records]
    margin_df = pd.DataFrame(margin_rows)
    if not margin_df.empty:
        margin_df = margin_df.sort_values("margin")

    # Backtest
    bt = result.backtest
    backtest_summary = pd.DataFrame([{
        "metryka": "agreement_rate", "wartość": round(bt.agreement_rate, 4)},
        {"metryka": "dopasowane_z_ręcznym", "wartość": bt.total_with_manual},
        {"metryka": "zgodne", "wartość": bt.agreements},
        {"metryka": "niezgodne", "wartość": bt.disagreements},
        {"metryka": "nieczytelne", "wartość": bt.unreadable_manual},
    ])
    backtest_mism = pd.DataFrame(bt.mismatches)

    tabs = [
        ("Cross_carrier", cross),
        ("Duble", duble),
        ("Przeplaty", przeplaty),
        ("Nieudane_obciazone", nieudane),
        ("Service_mismatch", service),
        ("Surcharge_outliers", surcharge),
        ("Zmiany_ops", ops),
        ("Weryfikacja_objetosci", volume),
        ("Osierocone", orphans),
        ("Nieobciazone", unbilled),
        ("Podsumowanie_per_przewoznik", summary),
        ("Uzgodnienie_FV", recon),
        ("Walidacja_vs_reczne", validation),
        ("Marza", margin_df),
        ("Backtest", backtest_summary),
        ("Backtest_niezgodnosci", backtest_mism),
    ]

    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        wb = writer.book
        hdr = wb.add_format({"bold": True, "bg_color": "#DDEBF7", "border": 1})
        flag_fmt = wb.add_format({"bg_color": "#FCE4E4"})
        for name, df in tabs:
            if df is None or df.empty:
                df = pd.DataFrame({"info": ["brak pozycji"]})
            df.to_excel(writer, sheet_name=name[:31], index=False)
            ws = writer.sheets[name[:31]]
            for col_idx, col in enumerate(df.columns):
                if len(df):
                    max_cell = max((len(str(v)) for v in df[col]), default=0)
                    width = min(48, max(12, max_cell + 2))
                else:
                    width = 16
                ws.set_column(col_idx, col_idx, width)
                ws.write(0, col_idx, str(col), hdr)


# --------------------------------------------------------------------------- #
# 3) reference_tariff.json
# --------------------------------------------------------------------------- #

def write_reference_tariff(result: PipelineResult, path: str | Path) -> None:
    result.tariff.save(path)


# --------------------------------------------------------------------------- #
# Generacja wszystkiego
# --------------------------------------------------------------------------- #

def generate_reports(result: PipelineResult, out_dir: str | Path,
                     cfg: Config | None = None) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "enriched_orders": str(out_dir / "enriched_orders.csv"),
        "audit_report": str(out_dir / "audit_report.xlsx"),
        "reference_tariff": str(out_dir / "reference_tariff.json"),
        "backtest": str(out_dir / "backtest.json"),
    }
    write_enriched_orders(result, paths["enriched_orders"], cfg)
    write_audit_report(result, paths["audit_report"], cfg)
    write_reference_tariff(result, paths["reference_tariff"])
    Path(paths["backtest"]).write_text(
        json.dumps(result.backtest.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8")
    return paths
