"""Adapter SPT — zestawienie PDF „flat" (§2.2).

Jedna linia = jedno zlecenie, jedyny koszt = `Cena transportu` (flat).
Poziom usługi z `Typ zamówienia` (`z wniesieniem` -> CARRY_IN; `zwykłe` ->
DOOR). `Stan` (`Odebrane`/`Nieodebrane`) -> status. Ostatnia linia
`PODSUMOWANIE` służy jako check, nie jako zlecenie.

UWAGA: parser PDF jest z natury kruchy (druk Symfonia). Rekomendacja procesowa
w README: poprosić SPT o XLSX/CSV zamiast PDF.
"""

from __future__ import annotations

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
    ("lp", ["lp."]),
    ("stan", ["stan"]),
    ("date", ["data"]),
    ("id_zam", ["id"]),
    ("order_ref", ["nr"]),
    ("order_type", ["typ"]),
    ("receiver", ["odbiorca"]),
    ("address", ["adres"]),
    ("products", ["produkty"]),
    ("cod", ["kwota"]),
    ("transport", ["cena"]),
]

_FOOTER = ("PODSUMOWANIE", "Suma")


class SptAdapter(CarrierAdapter):
    carrier = Carrier.SPT

    def parse(self, spec_path: str | Path) -> list[Delivery]:
        spec_path = Path(spec_path)
        records, _footer = parse_flat_table(
            spec_path,
            header_spec=_HEADER_SPEC,
            key_column="lp",
            footer_keywords=_FOOTER,
        )

        deliveries: list[Delivery] = []
        for rec in records:
            order_ref = rec.cells.get("order_ref", "").strip()
            if not order_ref:
                continue
            transport = parse_pl_number(rec.cells.get("transport", ""), default=0.0) or 0.0
            status = self.cfg.status_for(rec.cells.get("stan", ""))
            service_level = self.cfg.spt_service_level(rec.cells.get("order_type", ""))

            receiver = self._first_line(rec, "receiver")
            postcode = self._postcode_from(rec, "address")

            deliveries.append(Delivery(
                **self._base_delivery_kwargs(),
                order_ref_raw=order_ref,
                order_core=extract_core(order_ref),
                status=status,
                service_level=service_level,
                total_cost_net=transport,          # SPT: 1 komponent = cała Cena transportu
                fees=[FeeComponent(FeeType.TRANSPORT, "Cena transportu", transport)],
                receiver_name=receiver,
                receiver_postcode=postcode,
                delivery_date=rec.cells.get("date") or None,
                settlement_no=self.settlement_no,
                source_row=int(rec.lp) if rec.lp.isdigit() else None,
            ))
        return deliveries

    def stated_total(self, spec_path: str | Path) -> float | None:
        """Odczytaj deklarowaną sumę z linii `PODSUMOWANIE` (check)."""
        text = extract_full_text(spec_path)
        return find_amount_after(text, "PODSUMOWANIE", "RAZEM", "Netto")

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
