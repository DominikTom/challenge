"""Adapter Zadbano — zestawienie XLSX „itemized" (§2.3).

Format „long": wiersz-nagłówek zlecenia (ma `Nr zamówienia` + `Cena łączna za
zlecenie`) i pod nim N wierszy-komponentów opłaty (`Typ usługi` + `Opłata za
usługę`). Zadbano ma wiele komponentów kosztu -> tu żyje dwupoziomowy model
(Delivery + FeeComponent).

Plik ma zepsuty `xl/styles.xml`, więc czytamy surowy XML (``xlsx_raw``),
nie openpyxl.
"""

from __future__ import annotations

from pathlib import Path

from ..core.config import normalize_text
from ..core.models import (
    Carrier,
    Delivery,
    DeliveryStatus,
    FeeComponent,
    FeeType,
    ServiceLevel,
    extract_core,
)
from ..core.util import normalize_postcode, parse_pl_number
from ..core import xlsx_raw
from .base import CarrierAdapter

SHEET_ORDERS = "zlecenia"
SHEET_SUMMARY = "podsumowanie"
SHEET_INFO = "info"

# kanoniczne pole -> lista fragmentów nazwy nagłówka (znormalizowanych, substring)
_COLUMN_HINTS = {
    "order_ref": ["nr zamówienia", "nr zamowienia", "numer zamówienia"],
    "waybill": ["nr listu", "list przewozow"],
    "order_type": ["typ zlecenia"],
    "status": ["status realizacji", "status"],
    "standard": ["standard dostawy", "standard"],
    "qty": ["ilość szt", "ilosc szt", "ilość", "szt"],
    "weight": ["waga"],
    "volume": ["objętość", "objetosc"],
    "fee_type": ["typ usługi", "typ uslugi"],
    "fee_amount": ["opłata za usługę", "oplata za usluge", "opłata"],
    "total": ["cena łączna", "cena laczna", "łączna za zlecenie"],
    "receiver_city": ["odbiorca miasto", "miasto"],
    "receiver_postcode": ["odbiorca kod", "kod pocztowy", "kod"],
    "delivery_date": ["data doręczenia", "data doreczenia", "data realizacji"],
}


def _resolve_columns(headers: list[str]) -> dict[str, str | None]:
    """Zmapuj kanoniczne pola na rzeczywiste nazwy nagłówków (best-effort)."""
    norm = {h: normalize_text(h) for h in headers}
    resolved: dict[str, str | None] = {}
    for canonical, hints in _COLUMN_HINTS.items():
        found = None
        # najpierw dokładne dopasowanie fragmentu w kolejności podpowiedzi
        for hint in hints:
            for header, n in norm.items():
                if n == hint:
                    found = header
                    break
            if found:
                break
        if not found:
            for hint in hints:
                for header, n in norm.items():
                    if hint in n:
                        found = header
                        break
                if found:
                    break
        resolved[canonical] = found
    return resolved


class ZadbanoAdapter(CarrierAdapter):
    carrier = Carrier.ZADBANO

    def parse(self, spec_path: str | Path) -> list[Delivery]:
        records = xlsx_raw.read_sheet_records(spec_path, SHEET_ORDERS, header_row=0)
        if not records:
            return []
        headers = list(records[0].keys())
        cols = _resolve_columns(headers)

        deliveries: list[Delivery] = []
        current: Delivery | None = None

        for idx, rec in enumerate(records):
            order_ref = _get(rec, cols, "order_ref")
            fee_type_raw = _get(rec, cols, "fee_type")
            fee_amount_raw = _get(rec, cols, "fee_amount")

            if order_ref:
                # nowy nagłówek zlecenia -> domknij poprzedni
                if current is not None:
                    deliveries.append(current)
                current = self._start_delivery(rec, cols, order_ref, idx)

            if current is None:
                # komponent bez nagłówka (uszkodzony plik) — pomiń bezpiecznie
                continue

            # dołóż komponent, jeśli wiersz go niesie
            if fee_type_raw or fee_amount_raw:
                amount = parse_pl_number(fee_amount_raw, default=0.0) or 0.0
                current.fees.append(
                    FeeComponent(
                        type_code=self.cfg.fee_type_for(fee_type_raw or ""),
                        type_raw=(fee_type_raw or "").strip(),
                        amount_net=amount,
                    )
                )

        if current is not None:
            deliveries.append(current)

        # ustal total_cost_net: preferuj `Cena łączna`, w razie braku sumę komponentów
        for d in deliveries:
            if d.total_cost_net == 0.0 and d.fees:
                d.total_cost_net = d.fee_sum()
        return deliveries

    def _start_delivery(
        self, rec: dict, cols: dict, order_ref: str, idx: int
    ) -> Delivery:
        status = self.cfg.status_for(_get(rec, cols, "status"))
        service_level = self.cfg.zadbano_service_level(_get(rec, cols, "standard"))
        total = parse_pl_number(_get(rec, cols, "total"), default=0.0) or 0.0
        qty = parse_pl_number(_get(rec, cols, "qty"), default=None)
        weight = parse_pl_number(_get(rec, cols, "weight"), default=None)
        volume = parse_pl_number(_get(rec, cols, "volume"), default=None)
        postcode = normalize_postcode(_get(rec, cols, "receiver_postcode"))

        return Delivery(
            **self._base_delivery_kwargs(),
            order_ref_raw=order_ref,
            order_core=extract_core(order_ref),
            status=status,
            service_level=service_level,
            waybill=_get(rec, cols, "waybill") or None,
            qty=qty,
            weight_kg=weight,
            volume_m3=volume,
            total_cost_net=total,
            fees=[],
            receiver_postcode=postcode,
            receiver_city=_get(rec, cols, "receiver_city") or None,
            delivery_date=_get(rec, cols, "delivery_date") or None,
            settlement_no=self.settlement_no,
            source_row=idx,
        )


def _get(rec: dict, cols: dict, canonical: str) -> str:
    header = cols.get(canonical)
    if not header:
        return ""
    return (rec.get(header, "") or "").strip()


def parse_summary(spec_path: str | Path) -> dict:
    """Zparsuj arkusz `podsumowanie` -> {'categories': {...}, 'total': float}.

    Σ kategorii (bez wiersza `Total`) powinna = `Total` = netto FV (§2.3).
    """
    try:
        rows = xlsx_raw.read_sheet_rows(spec_path, SHEET_SUMMARY)
    except KeyError:
        return {"categories": {}, "total": None}

    categories: dict[str, float] = {}
    total: float | None = None
    for row in rows:
        cells = [c.strip() for c in row]
        if not any(cells):
            continue
        # znajdź pierwszą etykietę tekstową i ostatnią liczbę w wierszu
        label = None
        amount = None
        for c in cells:
            if label is None and c and parse_pl_number(c, default=None) is None:
                label = c
        for c in reversed(cells):
            val = parse_pl_number(c, default=None)
            if val is not None:
                amount = val
                break
        if label is None or amount is None:
            continue
        if normalize_text(label) in {"total", "razem", "suma", "grand total"}:
            total = amount
        else:
            categories[label] = amount
    return {"categories": categories, "total": total}


def parse_info(spec_path: str | Path) -> dict:
    """Zparsuj arkusz `info` (VendorID, BillingPeriodID, GeneratedAt)."""
    try:
        rows = xlsx_raw.read_sheet_rows(spec_path, SHEET_INFO)
    except KeyError:
        return {}
    info: dict[str, str] = {}
    for row in rows:
        cells = [c.strip() for c in row]
        if len(cells) >= 2 and cells[0]:
            info[cells[0]] = cells[1]
    return info
