"""Wspólne narzędzia: parsowanie liczb PL, dat, rozmiarów, kodów pocztowych."""

from __future__ import annotations

import re
from datetime import date, datetime

# --------------------------------------------------------------------------- #
# Liczby w formacie polskim ("1 234,56", "1.234,56", "455,00 zł", "—")
# --------------------------------------------------------------------------- #

_NUM_CLEAN_RE = re.compile(r"[^\d,.\-]")


def parse_pl_number(value, default: float | None = 0.0) -> float | None:
    """Zparsuj liczbę zapisaną po polsku na ``float``.

    Obsługuje: spacje/nbsp jako separator tysięcy, przecinek dziesiętny,
    kropkę tysięcy ("1.234,56"), symbole waluty, myślnik "—"/"-" jako 0/brak.
    Zwraca ``default`` dla wartości pustych/nieparsowalnych.
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s in {"-", "—", "–", "brak", "n/d", "nan", "NaN"}:
        return default
    # usuń wszystko poza cyframi, przecinkiem, kropką, minusem
    s = _NUM_CLEAN_RE.sub("", s)
    if not s or s in {"-", ".", ","}:
        return default

    has_dot = "." in s
    has_comma = "," in s
    if has_dot and has_comma:
        # oba obecne -> kropka = tysiące, przecinek = dziesiętne (format PL)
        s = s.replace(".", "").replace(",", ".")
    elif has_comma:
        # tylko przecinek -> dziesiętny
        s = s.replace(",", ".")
    # tylko kropka -> już poprawny (lub kropka to tysiące, ale wtedy i tak float OK)
    try:
        return float(s)
    except ValueError:
        return default


# --------------------------------------------------------------------------- #
# Daty
# --------------------------------------------------------------------------- #

_DATE_FORMATS = (
    "%Y-%m-%d",
    "%d.%m.%Y",
    "%d-%m-%Y",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%Y-%m-%d %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y %H:%M:%S",
)


def parse_date(value) -> date | None:
    """Zparsuj datę z typowych formatów PL/ISO. Zwraca ``date`` lub ``None``."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    # weź samą datę, gdy jest doklejony czas
    head = s.split()[0] if " " in s else s
    for candidate in (s, head):
        for fmt in _DATE_FORMATS:
            try:
                return datetime.strptime(candidate, fmt).date()
            except ValueError:
                continue
    # ostatnia próba: ISO z literą T
    try:
        return datetime.fromisoformat(s.replace("Z", "")).date()
    except ValueError:
        return None


def period_of(value) -> str | None:
    """Zwróć 'YYYY-MM' z daty/tekstu, albo ``None``."""
    d = parse_date(value)
    return f"{d.year:04d}-{d.month:02d}" if d else None


# --------------------------------------------------------------------------- #
# Rozmiar łóżka (Powierzchnia spania: 160cm x 200cm -> "160x200")
# --------------------------------------------------------------------------- #

_SIZE_RE = re.compile(
    r"(\d{2,3})\s*(?:cm)?\s*[x×]\s*(\d{2,3})\s*(?:cm)?", re.IGNORECASE
)


def extract_size_cm(text: str | None) -> str | None:
    """Wyciągnij rozmiar w formacie 'SZERxDL' z opisu opcji."""
    if not text:
        return None
    m = _SIZE_RE.search(str(text))
    if not m:
        return None
    return f"{m.group(1)}x{m.group(2)}"


# --------------------------------------------------------------------------- #
# Kod pocztowy
# --------------------------------------------------------------------------- #

_POSTCODE_RE = re.compile(r"\b(\d{2})-?(\d{3})\b")


def normalize_postcode(value: str | None) -> str | None:
    """Znormalizuj kod pocztowy do formatu 'NN-NNN' (albo ``None``)."""
    if not value:
        return None
    m = _POSTCODE_RE.search(str(value))
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}"


def postcode2(value: str | None) -> str | None:
    """Pierwsze dwie cyfry kodu pocztowego (klaster cennika, §6.5)."""
    pc = normalize_postcode(value)
    return pc[:2] if pc else None


# --------------------------------------------------------------------------- #
# Objętość / kubatura
# --------------------------------------------------------------------------- #

def volume_bucket(volume_m3: float | None) -> str:
    """Zgrupuj objętość w koszyk (klaster cennika, §6.5)."""
    if volume_m3 is None:
        return "NA"
    v = float(volume_m3)
    if v <= 0:
        return "0"
    if v < 0.15:
        return "XS"      # topper / drobne
    if v < 0.5:
        return "S"
    if v < 1.0:
        return "M"
    if v < 2.0:
        return "L"
    return "XL"          # łóżko + materac + stelaż
