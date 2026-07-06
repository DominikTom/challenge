"""Parser faktur zbiorczych PDF (§2.5) — kontrola sumy / referencja.

Wyciąga: nr faktury, sprzedawca, NIP, data, okres, netto, VAT, brutto,
termin płatności, oraz (dla D&M) numer rozliczenia, którego faktura dotyczy.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..core.models import Carrier, Invoice
from ..core.pdf_util import extract_full_text, find_amount_after
from ..core.util import parse_pl_number

_INVOICE_NO_RE = re.compile(
    r"(?:faktura(?:\s+vat)?|nr\s*faktury|numer\s+faktury)[:\s]*"
    r"([A-Z]{0,4}[0-9/][0-9A-Za-z/\-]+)",
    re.IGNORECASE,
)
_NIP_RE = re.compile(r"NIP[:\s]*([0-9][0-9\- ]{8,13})", re.IGNORECASE)
_SETTLEMENT_RE = re.compile(
    r"rozliczeni\w*\s*(?:nr[:.]?|numer[:.]?|o\s+numerze)?\s*([0-9]{1,4}/[0-9/]+)",
    re.IGNORECASE,
)
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2}|\d{2}[.\-/]\d{2}[.\-/]\d{4})")
_PERIOD_RE = re.compile(
    r"okres\w*[^:]{0,20}[:\s]+([0-9]{4}-[0-9]{2}|[0-9]{2}\.[0-9]{4}|\w+\s+\d{4})",
    re.IGNORECASE,
)


def parse_invoice(path: str | Path, carrier: Carrier | str) -> Invoice:
    """Sparsuj fakturę zbiorczą do :class:`Invoice`."""
    if isinstance(carrier, str):
        carrier = Carrier(carrier)
    path = Path(path)
    text = extract_full_text(path)

    invoice_no = _search(_INVOICE_NO_RE, text)
    nip = _clean_nip(_search(_NIP_RE, text))
    settlement_no = _search(_SETTLEMENT_RE, text)

    net = find_amount_after(text, "Wartość netto", "netto", "Razem netto")
    vat = find_amount_after(text, "VAT 23%", "VAT", "Kwota VAT")
    gross = find_amount_after(text, "Wartość brutto", "brutto", "Razem brutto")

    seller = _guess_seller(text)
    issue_date = _find_labeled_date(text, ["data wystawienia", "data faktury"])
    payment_due = _find_labeled_date(text, ["termin płatności", "termin platnosci"])
    period = _search(_PERIOD_RE, text)

    return Invoice(
        carrier=carrier,
        invoice_no=invoice_no or "",
        seller=seller,
        nip=nip,
        issue_date=issue_date,
        period=period,
        net=net,
        vat=vat,
        gross=gross,
        payment_due=payment_due,
        settlement_no=settlement_no,
        source_path=str(path),
    )


def _search(rx: re.Pattern, text: str) -> str | None:
    m = rx.search(text)
    return m.group(1).strip() if m else None


def _clean_nip(nip: str | None) -> str | None:
    if not nip:
        return None
    digits = re.sub(r"\D", "", nip)
    return digits or None


def _guess_seller(text: str) -> str | None:
    m = re.search(r"Sprzedawca[:\s]+(.+)", text, re.IGNORECASE)
    if m:
        return m.group(1).strip().split("\n")[0][:120]
    return None


def _find_labeled_date(text: str, labels: list[str]) -> str | None:
    low = text.lower()
    for label in labels:
        idx = low.find(label.lower())
        if idx < 0:
            continue
        tail = text[idx + len(label): idx + len(label) + 40]
        m = _DATE_RE.search(tail)
        if m:
            return m.group(1)
    return None
