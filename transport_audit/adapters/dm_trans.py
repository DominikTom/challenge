"""Adapter D&M Trans — zestawienie PDF „flat + usługi" (§2.4, §10).

Nagłówek: „Rozliczenie o numerze 07/02/2026 dla MyBed ...". Jedno zlecenie =
`TRANSPORT` (= `Koszt transportu netto`) + opcjonalnie `SERVICE`/`CARRY_IN`,
gdy `Usługi netto` > 0. Treść PDF bywa zdublowana (te same strony ×2) —
deduplikujemy bloki po (numer rozliczenia + Lp. + core) przed sumowaniem.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..core.models import (
    Carrier,
    Delivery,
    DeliveryStatus,
    FeeComponent,
    FeeType,
    ServiceLevel,
    extract_core,
)
from ..core.pdf_util import extract_full_text, find_amount_after, parse_flat_table
from ..core.util import normalize_postcode, parse_pl_number
from .base import CarrierAdapter

# nagłówek -> pierwsze słowo(a) kolumny (kolejność od lewej)
_HEADER_SPEC = [
    ("lp", ["l.p.", "lp"]),
    ("receiver", ["dane"]),
    ("order_ref", ["nr."]),
    ("desc", ["opis"]),
    ("params", ["parametry"]),
    ("packages", ["liczba"]),
    ("cod", ["pobranie"]),
    ("transport", ["koszt"]),
    ("services", ["uslugi", "usługi"]),
]

_SETTLEMENT_RE = re.compile(r"rozliczeni\w*\s+o\s+numerze\s+([0-9/\-]+)", re.IGNORECASE)
_WEIGHT_RE = re.compile(r"(-?\d+[.,]?\d*)\s*\[?\s*kg", re.IGNORECASE)
_VOLUME_RE = re.compile(r"(-?\d+[.,]?\d*)\s*\[?\s*m3", re.IGNORECASE)


class DmTransAdapter(CarrierAdapter):
    carrier = Carrier.DM_TRANS

    def parse(self, spec_path: str | Path) -> list[Delivery]:
        spec_path = Path(spec_path)
        full_text = extract_full_text(spec_path)
        settlement_no = self._detect_settlement_no(full_text)

        records, _footer = parse_flat_table(
            spec_path,
            header_spec=_HEADER_SPEC,
            key_column="lp",
            footer_keywords=("RAZEM", "Podsumowanie", "PODSUMOWANIE", "Koszt transportu netto"),
        )

        deliveries: list[Delivery] = []
        seen: set[tuple] = set()
        for rec in records:
            order_ref = rec.cells.get("order_ref", "").strip()
            if not order_ref:
                continue
            core = extract_core(order_ref)
            # DEDUP: (numer rozliczenia + Lp. + core) — odrzuca zdublowane strony
            dedup_key = (settlement_no, rec.lp, core, order_ref)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            transport = parse_pl_number(rec.cells.get("transport", ""), default=0.0) or 0.0
            services = parse_pl_number(rec.cells.get("services", ""), default=0.0) or 0.0
            weight, volume = self._parse_params(rec.cells.get("params", ""), rec.lines)
            qty = parse_pl_number(rec.cells.get("packages", ""), default=None)

            fees = [FeeComponent(FeeType.TRANSPORT, "Koszt transportu", transport)]
            service_level = ServiceLevel.DOOR
            if services and services > 0:
                fees.append(FeeComponent(FeeType.SERVICE, "Usługi", services))
                service_level = ServiceLevel.CARRY_IN

            receiver = self._first_line(rec, "receiver")
            postcode = self._postcode_from(rec, "receiver")

            deliveries.append(Delivery(
                **self._base_delivery_kwargs(),
                order_ref_raw=order_ref,
                order_core=core,
                status=DeliveryStatus.DELIVERED,   # rozliczenie zawiera zrealizowane
                service_level=service_level,
                qty=qty,
                weight_kg=weight,
                volume_m3=volume,
                total_cost_net=transport,          # §10: total = Koszt transportu netto
                fees=fees,
                receiver_name=receiver,
                receiver_postcode=postcode,
                settlement_no=settlement_no or self.settlement_no,
                source_row=int(rec.lp) if rec.lp.isdigit() else None,
            ))
        return deliveries

    def stated_total(self, spec_path: str | Path) -> float | None:
        """Odczytaj deklarowaną sumę „Koszt transportu netto" ze stopki (check)."""
        text = extract_full_text(spec_path)
        return find_amount_after(text, "Koszt transportu netto", "RAZEM")

    def _detect_settlement_no(self, text: str) -> str | None:
        m = _SETTLEMENT_RE.search(text)
        if m:
            return m.group(1).strip()
        return self.settlement_no

    @staticmethod
    def _parse_params(params_text: str, lines: dict) -> tuple[float | None, float | None]:
        text = params_text
        # parametry bywają w 2 liniach: "45 [kg]" i "0.9 [m3]"
        joined = " ".join(lines.get("params", [])) or text
        w = _WEIGHT_RE.search(joined)
        v = _VOLUME_RE.search(joined)
        weight = parse_pl_number(w.group(1), default=None) if w else None
        volume = parse_pl_number(v.group(1), default=None) if v else None
        return weight, volume

    @staticmethod
    def _first_line(rec, key: str) -> str | None:
        vals = rec.lines.get(key, [])
        return vals[0].strip() if vals else (rec.cells.get(key) or None)

    @staticmethod
    def _postcode_from(rec, key: str) -> str | None:
        for line in rec.lines.get(key, []):
            pc = normalize_postcode(line)
            if pc:
                return pc
        return normalize_postcode(rec.cells.get(key, ""))
