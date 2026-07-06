"""Wczytanie eksportu ERP (`Eksport.csv`) — źródło prawdy o treści zamówienia.

Format „long": pierwszy wiersz zamówienia ma wypełnioną kolumnę `Numer`,
kolejne wiersze z pustym `Numer` to dalsze pozycje/tagi tego samego
zamówienia. Robimy forward-fill `Numer`, grupujemy, i wyprowadzamy poziom
usługi z pozycji-usług oraz rozmiary z `Pozycje zamówienia/Opcja`.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .config import Config, load_config, normalize_text
from .models import ErpOrder, ServiceLevel, extract_core
from .util import extract_size_cm, normalize_postcode, parse_date, parse_pl_number

# Kanoniczne nazwy kolumn (§2.1)
COL_NUMBER = "Numer"
COL_ORDER_DATE = "Data zamówienia"
COL_PRODUCT = "Pozycje zamówienia/Produkt/Nazwa"
COL_QTY = "Pozycje zamówienia/Ilość"
COL_OPTION = "Pozycje zamówienia/Opcja"
COL_DELIVERY_METHOD = "Metoda dostawy"
COL_POSTCODE = "Kod pocztowy"
COL_CITY = "Miasto"
COL_TOTAL = "Suma"
COL_DELIVERY_FEE = "Koszt dostawy"
COL_STATUS = "Status"
COL_TAGS = "Tagi"
COL_TRANSPORT_INVOICE = "Faktura transportowa"
COL_CUSTOMER_NAME = "Klient/Nazwa"
COL_STREET = "Adres dostawy/Ulica"

_PREFIX_RE = None  # lazily unused; prefix wyliczamy prostym skanem liter


def _extract_prefix(number: str | None) -> str | None:
    """Wyodrębnij prefiks numeru (Shoper/Shopify/ZAM/Amazon/...)."""
    if not number:
        return None
    letters = []
    for ch in str(number):
        if ch.isalpha():
            letters.append(ch)
        else:
            break
    return "".join(letters) or None


def _sniff_dialect(path: Path) -> tuple[str, str]:
    """Wykryj kodowanie i separator CSV (PL eksporty bywają cp1250 / ';')."""
    encodings = ["utf-8-sig", "utf-8", "cp1250", "latin-1"]
    sample = None
    used_encoding = "utf-8"
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as fh:
                sample = fh.read(8192)
            used_encoding = enc
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if sample is None:
        return "utf-8", ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        sep = dialect.delimiter
    except csv.Error:
        # heurystyka: policz kandydatów w pierwszej linii
        first_line = sample.splitlines()[0] if sample else ""
        sep = ";" if first_line.count(";") > first_line.count(",") else ","
    return used_encoding, sep


def load_erp_dataframe(path: str | Path) -> pd.DataFrame:
    """Wczytaj CSV jako DataFrame stringów z forward-fill kolumny `Numer`."""
    path = Path(path)
    encoding, sep = _sniff_dialect(path)
    df = pd.read_csv(
        path,
        dtype=str,
        sep=sep,
        encoding=encoding,
        keep_default_na=False,
        na_filter=False,
    )
    df.columns = [str(c).strip() for c in df.columns]
    if COL_NUMBER not in df.columns:
        raise ValueError(
            f"Brak kolumny '{COL_NUMBER}' w {path.name}. "
            f"Znalezione kolumny: {list(df.columns)[:5]}..."
        )
    # forward-fill: puste '' -> ostatni niepusty Numer
    numbers = df[COL_NUMBER].astype(str).str.strip()
    numbers = numbers.where(numbers != "", other=pd.NA).ffill()
    df[COL_NUMBER] = numbers
    # odrzuć wiersze przed pierwszym numerem (gdyby jakieś były)
    df = df[df[COL_NUMBER].notna()].copy()
    return df


@dataclass
class ErpDataset:
    """Zbiór zamówień ERP + indeksy do złączenia (§4)."""

    orders: list[ErpOrder]
    by_number: dict[str, ErpOrder] = field(default_factory=dict)
    by_core: dict[str, list[ErpOrder]] = field(default_factory=dict)

    def get_by_core(self, core: str | None) -> list[ErpOrder]:
        if core is None:
            return []
        return self.by_core.get(core, [])


def _derive_service_level(product_names: list[str], cfg: Config) -> ServiceLevel:
    """Najwyższy poziom usługi obecny wśród pozycji-usług zamówienia."""
    best = ServiceLevel.DOOR  # domyślnie dostawa pod drzwi (jest `Wysyłka`)
    found_any = False
    for name in product_names:
        level = cfg.service_level_for_item(name)
        if level is not None:
            found_any = True
            if level.rank > best.rank:
                best = level
    return best if found_any else ServiceLevel.UNKNOWN


def build_orders(df: pd.DataFrame, cfg: Config | None = None) -> list[ErpOrder]:
    """Zbuduj listę :class:`ErpOrder` z DataFrame (po forward-fill)."""
    cfg = cfg or load_config()
    has = {c: (c in df.columns) for c in [
        COL_ORDER_DATE, COL_PRODUCT, COL_OPTION, COL_DELIVERY_METHOD,
        COL_POSTCODE, COL_CITY, COL_TOTAL, COL_DELIVERY_FEE, COL_STATUS,
        COL_TAGS, COL_TRANSPORT_INVOICE, COL_CUSTOMER_NAME, COL_STREET,
    ]}

    orders: list[ErpOrder] = []
    # zachowujemy kolejność wystąpienia zamówień
    for number, group in df.groupby(COL_NUMBER, sort=False):
        header = group.iloc[0]
        row_index = int(group.index[0])

        # pozycje: rozdziel na produkty (realne) i pozycje-usługi
        product_names: list[str] = []
        sizes: list[str] = []
        if has[COL_PRODUCT]:
            for _, row in group.iterrows():
                raw_name = str(row.get(COL_PRODUCT, "")).strip()
                if not raw_name:
                    continue
                product_names.append(raw_name)
                if has[COL_OPTION]:
                    size = extract_size_cm(row.get(COL_OPTION, ""))
                    if size and size not in sizes:
                        sizes.append(size)

        service_level = _derive_service_level(product_names, cfg)
        # produkty = pozycje, które NIE są usługami
        real_products = [
            n for n in product_names if cfg.service_level_for_item(n) is None
        ]

        def hv(col: str) -> str:
            return str(header.get(col, "")).strip() if has[col] else ""

        tags_raw = hv(COL_TAGS)
        tags = [t.strip() for t in tags_raw.replace(";", ",").split(",") if t.strip()]

        existing_inv = hv(COL_TRANSPORT_INVOICE) or None

        order = ErpOrder(
            number=str(number),
            core=extract_core(str(number)),
            order_date=hv(COL_ORDER_DATE) or None,
            products=real_products,
            service_level=service_level,
            sizes_cm=sizes,
            postcode=normalize_postcode(hv(COL_POSTCODE)) or (hv(COL_POSTCODE) or None),
            city=hv(COL_CITY) or None,
            delivery_fee_charged=parse_pl_number(hv(COL_DELIVERY_FEE)) or 0.0,
            order_total=parse_pl_number(hv(COL_TOTAL)) or 0.0,
            status=hv(COL_STATUS) or None,
            tags=tags,
            existing_transport_invoice=existing_inv,
            prefix=_extract_prefix(str(number)),
            delivery_method=hv(COL_DELIVERY_METHOD) or None,
            receiver_name=hv(COL_CUSTOMER_NAME) or None,
            street=hv(COL_STREET) or None,
            row_index=row_index,
        )
        orders.append(order)
    return orders


def build_dataset(orders: list[ErpOrder]) -> ErpDataset:
    """Zbuduj indeksy ``by_number`` i ``by_core`` (kolizje -> lista)."""
    by_number: dict[str, ErpOrder] = {}
    by_core: dict[str, list[ErpOrder]] = defaultdict(list)
    for order in orders:
        by_number[order.number] = order
        if order.core:
            by_core[order.core].append(order)
    return ErpDataset(orders=orders, by_number=by_number, by_core=dict(by_core))


def load_erp(path: str | Path, cfg: Config | None = None) -> ErpDataset:
    """Pełne wczytanie ERP: CSV -> forward-fill -> grupowanie -> indeksy."""
    cfg = cfg or load_config()
    df = load_erp_dataframe(path)
    orders = build_orders(df, cfg)
    return build_dataset(orders)


def orders_in_period(orders: list[ErpOrder], period: str) -> list[ErpOrder]:
    """Zamówienia z danego okresu 'YYYY-MM' (po `Data zamówienia`)."""
    result = []
    for o in orders:
        d = parse_date(o.order_date)
        if d and f"{d.year:04d}-{d.month:02d}" == period:
            result.append(o)
    return result
