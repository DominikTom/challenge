"""Złączenie linii kosztu (`Delivery`) z zamówieniami ERP (§4).

Kolejność:
1. po `core` (mapa core -> ErpOrder; kolizje prefiksów rozstrzygamy prefiksem,
   potem kodem pocztowym),
2. fallback fuzzy: (nazwisko odbiorcy + kod pocztowy) w oknie ±14 dni,
   podobieństwo rapidfuzz >= próg,
3. brak dopasowania -> orphan.

Odwrotnie: zamówienia ERP w okresie z pozycją Wysyłka/wniesienie bez żadnej
linii kosztu -> unbilled.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .config import Config, load_config, strip_diacritics
from .erp import ErpDataset, orders_in_period
from .models import Delivery, ErpOrder, MatchResult, ServiceLevel
from .util import parse_date


def _norm_name(name: str | None) -> str:
    if not name:
        return ""
    return " ".join(strip_diacritics(name).lower().split())


@dataclass
class MatchOutcome:
    """Wynik złączenia całego okresu."""

    matches: list[MatchResult] = field(default_factory=list)
    orphans: list[Delivery] = field(default_factory=list)
    unbilled: list[ErpOrder] = field(default_factory=list)

    def matched_deliveries(self) -> list[MatchResult]:
        return [m for m in self.matches if m.is_matched]

    def by_core(self) -> dict[str, list[MatchResult]]:
        out: dict[str, list[MatchResult]] = {}
        for m in self.matches:
            key = m.delivery.order_core or f"__ref__{m.delivery.order_ref_raw}"
            out.setdefault(key, []).append(m)
        return out


class Matcher:
    def __init__(self, erp: ErpDataset, cfg: Config | None = None) -> None:
        self.erp = erp
        self.cfg = cfg or load_config()
        self.fuzzy_threshold = self.cfg.threshold("fuzzy_threshold")
        self.date_window = int(self.cfg.threshold("fuzzy_date_window_days"))

    # -- dopasowanie pojedynczej linii ------------------------------------- #

    def match_one(self, delivery: Delivery) -> MatchResult:
        # 1) po core
        if delivery.order_core:
            candidates = self.erp.get_by_core(delivery.order_core)
            if candidates:
                erp_order, method = self._resolve_core(delivery, candidates)
                return MatchResult(delivery, erp_order, match_method=method)
        # 2) fuzzy fallback
        fuzzy = self._match_fuzzy(delivery)
        if fuzzy is not None:
            erp_order, score = fuzzy
            return MatchResult(delivery, erp_order, match_method="fuzzy", score=score)
        # 3) orphan
        return MatchResult(delivery, None, match_method="orphan")

    def _resolve_core(
        self, delivery: Delivery, candidates: list[ErpOrder]
    ) -> tuple[ErpOrder, str]:
        if len(candidates) == 1:
            return candidates[0], "core"
        # kolizja prefiksów: rozstrzygnij po prefiksie w order_ref
        ref_low = strip_diacritics(delivery.order_ref_raw).lower()
        by_prefix = [
            c for c in candidates
            if c.prefix and c.prefix.lower() in ref_low
        ]
        pool = by_prefix or candidates
        if len(pool) == 1:
            return pool[0], "core+prefix"
        # dalej rozstrzygnij po kodzie pocztowym
        if delivery.receiver_postcode:
            by_pc = [c for c in pool if c.postcode == delivery.receiver_postcode]
            if len(by_pc) == 1:
                return by_pc[0], "core+postcode"
            if by_pc:
                pool = by_pc
        return pool[0], "core+ambiguous"

    def _match_fuzzy(self, delivery: Delivery) -> tuple[ErpOrder, float] | None:
        target_name = _norm_name(delivery.receiver_name)
        if not target_name:
            return None
        d_date = parse_date(delivery.delivery_date)
        best: tuple[ErpOrder, float] | None = None
        for order in self.erp.orders:
            # twardy filtr: kod pocztowy musi się zgadzać (jeśli znany po obu stronach)
            if delivery.receiver_postcode and order.postcode:
                if delivery.receiver_postcode != order.postcode:
                    continue
            # okno czasowe ±N dni (gdy obie daty znane)
            if d_date and order.order_date:
                o_date = parse_date(order.order_date)
                if o_date and abs((o_date - d_date).days) > self.date_window:
                    continue
            cand_name = _norm_name(order.receiver_name)
            if not cand_name:
                continue
            score = fuzz.token_sort_ratio(target_name, cand_name)
            if score >= self.fuzzy_threshold and (best is None or score > best[1]):
                best = (order, score)
        return best

    # -- dopasowanie całego okresu ----------------------------------------- #

    def run(self, deliveries: list[Delivery], period: str) -> MatchOutcome:
        outcome = MatchOutcome()
        matched_order_numbers: set[str] = set()
        for delivery in deliveries:
            result = self.match_one(delivery)
            outcome.matches.append(result)
            if result.is_matched:
                matched_order_numbers.add(result.erp_order.number)
            else:
                outcome.orphans.append(result.delivery)

        # unbilled: ERP w okresie z usługą wysyłki/wniesienia bez linii kosztu
        shippable = {
            ServiceLevel.DOOR, ServiceLevel.CARRY_IN, ServiceLevel.CARRY_IN_ASSEMBLY
        }
        for order in orders_in_period(self.erp.orders, period):
            if order.service_level in shippable and order.number not in matched_order_numbers:
                outcome.unbilled.append(order)
        return outcome
