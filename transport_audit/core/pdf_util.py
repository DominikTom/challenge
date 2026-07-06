"""Narzędzia do parsowania PDF „flat" (SPT, D&M) przez rekonstrukcję kolumn.

Strategia (odporna, nie „na sztywno"): wykrywamy pozycje X kolumn z WIERSZA
NAGŁÓWKA (a nie hardkodujemy), potem przypisujemy słowa danych do kolumn po
współrzędnej X. Wiersze wieloliniowe (adres/opis) scalamy po pierwszej kolumnie
(Lp.). Dzięki temu parser adaptuje się do układu strony i działa też, gdy
kolumny lekko się przesuną.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pdfplumber

from .config import strip_diacritics


@dataclass
class Word:
    text: str
    x0: float
    x1: float
    top: float
    bottom: float

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2.0


@dataclass
class Column:
    key: str
    x_left: float
    x_right: float


def _norm(text: str) -> str:
    return strip_diacritics(text).lower().strip()


def extract_pages_words(path: str | Path) -> list[list[Word]]:
    """Zwróć listę stron; każda strona = lista :class:`Word`."""
    pages: list[list[Word]] = []
    with pdfplumber.open(str(path)) as pdf:
        for page in pdf.pages:
            words = [
                Word(w["text"], w["x0"], w["x1"], w["top"], w["bottom"])
                for w in page.extract_words(use_text_flow=False, keep_blank_chars=False)
            ]
            pages.append(words)
    return pages


def extract_full_text(path: str | Path) -> str:
    with pdfplumber.open(str(path)) as pdf:
        return "\n".join((page.extract_text() or "") for page in pdf.pages)


def cluster_rows(words: list[Word], y_tol: float = 3.0) -> list[list[Word]]:
    """Pogrupuj słowa w wiersze po współrzędnej `top`; posortuj po X w wierszu."""
    if not words:
        return []
    ordered = sorted(words, key=lambda w: (round(w.top, 1), w.x0))
    rows: list[list[Word]] = []
    current: list[Word] = []
    current_top: float | None = None
    for w in ordered:
        if current_top is None or abs(w.top - current_top) <= y_tol:
            current.append(w)
            current_top = w.top if current_top is None else current_top
        else:
            rows.append(sorted(current, key=lambda x: x.x0))
            current = [w]
            current_top = w.top
    if current:
        rows.append(sorted(current, key=lambda x: x.x0))
    return rows


def detect_columns(
    rows: list[list[Word]], header_spec: list[tuple[str, list[str]]]
) -> tuple[list[Column], int]:
    """Wykryj granice kolumn na podstawie wiersza nagłówka.

    ``header_spec`` = lista (klucz, [warianty pierwszego słowa nagłówka]) w
    kolejności od lewej. Zwraca (kolumny, indeks_wiersza_nagłówka).
    """
    anchor_sets = [
        (key, [_norm(v) for v in variants]) for key, variants in header_spec
    ]

    def row_score(row: list[Word]) -> int:
        toks = [_norm(w.text) for w in row]
        score = 0
        for _key, variants in anchor_sets:
            if any(any(tok.startswith(v) or v in tok for v in variants) for tok in toks):
                score += 1
        return score

    header_idx = max(range(len(rows)), key=lambda i: row_score(rows[i])) if rows else -1
    if header_idx < 0 or row_score(rows[header_idx]) < max(2, len(header_spec) // 2):
        return [], -1

    # zbierz słowa z pasma nagłówka (nagłówek może być w 2 liniach)
    header_top = rows[header_idx][0].top
    band_words: list[Word] = []
    for row in rows:
        if row and abs(row[0].top - header_top) <= 16:
            band_words.extend(row)

    # dla każdej kolumny znajdź x0 pierwszego pasującego słowa
    positions: list[tuple[str, float]] = []
    for key, variants in anchor_sets:
        best_x: float | None = None
        for w in sorted(band_words, key=lambda x: x.x0):
            tok = _norm(w.text)
            if any(tok.startswith(v) or v == tok for v in variants):
                best_x = w.x0
                break
        if best_x is not None:
            positions.append((key, best_x))

    positions.sort(key=lambda p: p[1])
    columns: list[Column] = []
    for i, (key, x_left) in enumerate(positions):
        x_right = positions[i + 1][1] - 1.0 if i + 1 < len(positions) else float("inf")
        columns.append(Column(key=key, x_left=x_left - 3.0, x_right=x_right))
    return columns, header_idx


def assign_columns(row: list[Word], columns: list[Column]) -> dict[str, str]:
    """Przypisz słowa wiersza do kolumn po X; sklej tekst w komórkach."""
    cells: dict[str, list[str]] = {c.key: [] for c in columns}
    for w in row:
        for c in columns:
            if c.x_left <= w.xc < c.x_right:
                cells[c.key].append(w.text)
                break
    return {k: " ".join(v).strip() for k, v in cells.items()}


_INT_RE = re.compile(r"^\d+$")


@dataclass
class FlatRecord:
    cells: dict[str, str]           # scalone komórki (klucz kolumny -> tekst)
    lines: dict[str, list[str]]     # per kolumna: kolejne linie fizyczne
    page: int
    lp: str


def parse_flat_table(
    path: str | Path,
    header_spec: list[tuple[str, list[str]]],
    key_column: str,
    footer_keywords: tuple[str, ...] = (),
) -> tuple[list[FlatRecord], list[str]]:
    """Sparsuj PDF „flat" do rekordów; scal wiersze wieloliniowe po `key_column`.

    Zwraca (rekordy, footer_lines). ``key_column`` to kolumna z Lp./L.p.:
    nowy rekord zaczyna się, gdy ta kolumna zawiera liczbę.
    """
    pages = extract_pages_words(path)
    records: list[FlatRecord] = []
    footer_lines: list[str] = []
    footer_norm = tuple(_norm(k) for k in footer_keywords)

    for page_no, words in enumerate(pages):
        rows = cluster_rows(words)
        columns, header_idx = detect_columns(rows, header_spec)
        if not columns:
            continue
        current: FlatRecord | None = None
        for row in rows[header_idx + 1:]:
            cells = assign_columns(row, columns)
            # wykryj wiersz nagłówka powtórzony na kolejnej stronie -> pomiń
            joined_norm = _norm(" ".join(cells.values()))
            if footer_norm and any(fk and joined_norm.startswith(fk) for fk in footer_norm):
                footer_lines.append(" ".join(w.text for w in row))
                continue
            if any(_norm(v) in {_norm(h) for _, hs in header_spec for h in hs}
                   for v in [cells.get(key_column, "")]) and not cells.get(key_column):
                continue

            key_val = cells.get(key_column, "").strip()
            is_start = bool(_INT_RE.match(key_val))
            if is_start:
                if current is not None:
                    records.append(current)
                current = FlatRecord(cells=dict(cells),
                                     lines={k: [v] for k, v in cells.items()},
                                     page=page_no, lp=key_val)
            else:
                if current is None:
                    continue  # śmieci przed pierwszym rekordem
                # dołącz linię kontynuacji do bieżącego rekordu
                for k, v in cells.items():
                    if v:
                        current.cells[k] = (current.cells[k] + " " + v).strip() if current.cells.get(k) else v
                        current.lines.setdefault(k, []).append(v)
        if current is not None:
            records.append(current)
            current = None
    return records, footer_lines


_AMOUNT_RE = re.compile(r"(-?\d[\d  .]*,\d{2}|-?\d[\d  .]*\.\d{2}|-?\d+)")


def find_amount_after(text: str, *keywords: str) -> float | None:
    """Znajdź kwotę występującą po którymś ze słów kluczowych w tekście."""
    from .util import parse_pl_number

    norm_text = strip_diacritics(text).lower()
    for kw in keywords:
        k = strip_diacritics(kw).lower()
        idx = norm_text.find(k)
        if idx < 0:
            continue
        tail = text[idx + len(kw):]
        m = _AMOUNT_RE.search(tail)
        if m:
            val = parse_pl_number(m.group(1), default=None)
            if val is not None:
                return val
    return None
