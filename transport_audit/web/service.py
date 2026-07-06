"""Serwis web: uruchom pipeline z plików i zbuduj JSON-owe podsumowanie
+ pliki wynikowe (base64) do pobrania w przeglądarce.

Bezstanowo (Vercel serverless nie ma trwałego dysku): pliki wejściowe lądują
w katalogu tymczasowym, wyjścia czytamy z powrotem i zwracamy jako base64.
"""

from __future__ import annotations

import base64
import tempfile
from collections import Counter
from pathlib import Path

from ..core.models import Severity
from ..core.pipeline import CarrierInput, run_pipeline
from ..report import generate_reports

# ile pozycji per kategoria pokazać w UI (pełne dane są w audit_report.xlsx)
_MAX_FINDINGS = 200


def _flag_row(f) -> dict:
    return {
        "order_core": f.order_core,
        "order_number": f.order_number,
        "carrier": f.carrier,
        "severity": f.severity.value,
        "message": f.message,
        "amount": f.amount,
        "expected": f.expected,
        "recoverable": f.recoverable,
        "evidence": f.evidence,
    }


def build_summary(result) -> dict:
    from ..core.anomalies import (
        R_CROSS, R_DOUBLE, R_FAILED, R_SERVICE, R_TARIFF, R_SURCHARGE,
        R_VOLUME, R_OPS,
    )

    audit = result.audit
    counts: Counter = Counter((f.rule, f.severity.value) for f in audit.flags)
    rules = sorted({r for r, _ in counts})
    flags_by_rule = [
        {
            "rule": rule,
            "FLAG": counts.get((rule, "FLAG"), 0),
            "WARN": counts.get((rule, "WARN"), 0),
            "INFO": counts.get((rule, "INFO"), 0),
        }
        for rule in rules
    ]

    total_flags = sum(1 for f in audit.flags if f.severity is Severity.FLAG)
    recoverable = round(sum(
        f.recoverable or 0 for f in audit.flags
        if f.rule in (R_CROSS, R_DOUBLE, R_FAILED)), 2)

    reconciliation = [
        {
            "carrier": r.carrier,
            "invoice_no": r.invoice_no,
            "settlement_no": r.settlement_no,
            "actual_sum": r.actual_sum,
            "expected_net": r.expected_net,
            "delta": r.delta,
            "within_tolerance": r.within_tolerance,
        }
        for r in result.recon_results
    ]

    def rows(rule, limit=_MAX_FINDINGS):
        return [_flag_row(f) for f in audit.by_rule(rule)][:limit]

    findings = {
        "cross_carrier": sorted(rows(R_CROSS), key=lambda x: -(x["recoverable"] or 0)),
        "double": rows(R_DOUBLE),
        "failed_charged": rows(R_FAILED),
        "service_mismatch": rows(R_SERVICE),
        "above_tariff": [r for r in rows(R_TARIFF) if r["severity"] == "FLAG"],
        "surcharge_outliers": rows(R_SURCHARGE),
        "volume_recheck": rows(R_VOLUME),
        "ops_changes": rows(R_OPS),
    }

    orphans = [
        {"order_ref_raw": o.order_ref_raw, "order_core": o.order_core,
         "carrier": o.carrier.value, "total_cost_net": round(o.total_cost_net, 2),
         "receiver": o.receiver_name}
        for o in result.outcome.orphans
    ][:_MAX_FINDINGS]
    unbilled = [
        {"number": o.number, "service_level": o.service_level.value,
         "city": o.city, "order_date": o.order_date}
        for o in result.outcome.unbilled
    ][:_MAX_FINDINGS]

    return {
        "period": result.period,
        "reconciliation": reconciliation,
        "reconcile_ok": all(r.within_tolerance for r in result.recon_results),
        "flags_by_rule": flags_by_rule,
        "total_flags": total_flags,
        "recoverable_estimate": recoverable,
        "backtest": {
            "agreement_rate": round(result.backtest.agreement_rate, 4),
            "total_with_manual": result.backtest.total_with_manual,
            "disagreements": result.backtest.disagreements,
        },
        "counts": {
            "deliveries": len(result.deliveries),
            "matched": len(result.outcome.matched_deliveries()),
            "orphans": len(result.outcome.orphans),
            "unbilled": len(result.outcome.unbilled),
            "erp_orders": len(result.erp.orders),
        },
        "margin": result.margins.to_summary(),
        "findings": findings,
        "orphans": orphans,
        "unbilled": unbilled,
    }


def _b64_file(path: Path) -> dict:
    data = path.read_bytes()
    return {
        "filename": path.name,
        "size": len(data),
        "base64": base64.b64encode(data).decode("ascii"),
    }


def run_audit(erp_path: str | None, carrier_inputs: list[CarrierInput], period: str,
              erp_source: str = "file", save_supabase: bool = False) -> dict:
    """Uruchom pełny pipeline i zwróć podsumowanie + pliki (base64).

    ``erp_source``: 'file' albo 'supabase'. ``save_supabase``: upsert wyników
    do fact_delivery_costs + reconciliation_log.
    """
    result = run_pipeline(erp_path, carrier_inputs, period, erp_source=erp_source)
    summary = build_summary(result)
    summary["erp_source"] = erp_source

    out_dir = Path(tempfile.mkdtemp(prefix="ta_out_"))
    paths = generate_reports(result, out_dir)
    summary["files"] = {
        "audit_report": _b64_file(Path(paths["audit_report"])),
        "enriched_orders": _b64_file(Path(paths["enriched_orders"])),
        "reference_tariff": _b64_file(Path(paths["reference_tariff"])),
    }

    if save_supabase:
        from ..core.supabase_io import write_results
        try:
            summary["supabase_write"] = write_results(result)
        except Exception as exc:  # noqa: BLE001
            summary["supabase_write"] = {"status": "error",
                                         "error": f"{type(exc).__name__}: {exc}"}
    return summary
