"""Backtest matchera (§9): odczyt przewoźnika z ~15k historycznych ręcznych
wpisów `Faktura transportowa` i porównanie z auto-przypisaniem.

Format wpisu: `"<nr faktury> <PRZEWOŹNIK>"`, np. `FS/38/02/2026 SPT`,
`307/02/2026/TR ZADBANO`, `FS/24/02/2026 D&M TRANS`. Przewoźnik to sufiks.
Cel: >= 98% zgodności przewoźnika na dopasowanych liniach.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .config import Config, load_config, strip_diacritics
from .models import Carrier, MatchResult


def carrier_from_manual_entry(entry: str | None, cfg: Config | None = None) -> Carrier | None:
    """Odczytaj kod przewoźnika z ręcznego wpisu `Faktura transportowa`."""
    if not entry:
        return None
    cfg = cfg or load_config()
    norm = strip_diacritics(entry).upper()
    # dopasuj po aliasach; wybierz alias najdłuższy i najbardziej „na końcu"
    best: tuple[int, int, Carrier] | None = None  # (pozycja, długość, carrier)
    for code, aliases in cfg.carrier_aliases.items():
        for alias in aliases:
            a = strip_diacritics(alias).upper()
            pos = norm.rfind(a)
            if pos >= 0:
                key = (pos, len(a))
                if best is None or key > (best[0], best[1]):
                    best = (pos, len(a), Carrier(code))
    return best[2] if best else None


@dataclass
class BacktestReport:
    total_with_manual: int = 0
    agreements: int = 0
    disagreements: int = 0
    unreadable_manual: int = 0
    per_carrier: dict[str, dict[str, int]] = field(default_factory=dict)
    mismatches: list[dict] = field(default_factory=list)

    @property
    def agreement_rate(self) -> float:
        base = self.agreements + self.disagreements
        return (self.agreements / base) if base else 1.0

    def precision_recall(self) -> dict[str, dict[str, float]]:
        """Precision/recall per przewoźnik (auto vs ręczny jako ground truth)."""
        out: dict[str, dict[str, float]] = {}
        for code, stats in self.per_carrier.items():
            tp = stats.get("tp", 0)
            fp = stats.get("fp", 0)
            fn = stats.get("fn", 0)
            precision = tp / (tp + fp) if (tp + fp) else 1.0
            recall = tp / (tp + fn) if (tp + fn) else 1.0
            out[code] = {"precision": round(precision, 4), "recall": round(recall, 4),
                         "tp": tp, "fp": fp, "fn": fn}
        return out

    def to_dict(self) -> dict:
        return {
            "total_with_manual": self.total_with_manual,
            "agreements": self.agreements,
            "disagreements": self.disagreements,
            "unreadable_manual": self.unreadable_manual,
            "agreement_rate": round(self.agreement_rate, 4),
            "precision_recall": self.precision_recall(),
            "mismatches": self.mismatches[:200],
        }


def run_backtest(matches: list[MatchResult], cfg: Config | None = None) -> BacktestReport:
    """Porównaj auto-przypisanie przewoźnika z historycznym wpisem ręcznym."""
    cfg = cfg or load_config()
    report = BacktestReport()
    per: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for m in matches:
        if not m.is_matched:
            continue
        manual_raw = m.erp_order.existing_transport_invoice
        if not manual_raw:
            continue
        report.total_with_manual += 1
        manual_carrier = carrier_from_manual_entry(manual_raw, cfg)
        if manual_carrier is None:
            report.unreadable_manual += 1
            continue
        auto_carrier = m.delivery.carrier
        if auto_carrier == manual_carrier:
            report.agreements += 1
            per[auto_carrier.value]["tp"] += 1
        else:
            report.disagreements += 1
            per[auto_carrier.value]["fp"] += 1
            per[manual_carrier.value]["fn"] += 1
            report.mismatches.append({
                "order_number": m.erp_order.number,
                "order_core": m.delivery.order_core,
                "auto": auto_carrier.value,
                "manual": manual_carrier.value,
                "manual_raw": manual_raw,
            })
    report.per_carrier = {k: dict(v) for k, v in per.items()}
    return report
