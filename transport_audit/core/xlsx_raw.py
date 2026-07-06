"""Surowy czytnik XLSX (zipfile + xml.etree), odporny na zepsuty `styles.xml`.

Plik Zadbano (`307_02_2026_TR_specyfikacja.xlsx`) ma uszkodzony
`xl/styles.xml`, przez co ``openpyxl.load_workbook`` wywala
``Fill() takes no arguments``. Ten czytnik NIE dotyka styles.xml —
czyta tylko `sharedStrings.xml`, `workbook.xml` i arkusze, więc otwiera
plik niezależnie od stylów.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}

_CELL_REF_RE = re.compile(r"([A-Z]+)(\d+)")


def _col_to_index(col_letters: str) -> int:
    """'A' -> 0, 'B' -> 1, ... 'AA' -> 26."""
    idx = 0
    for ch in col_letters:
        idx = idx * 26 + (ord(ch) - ord("A") + 1)
    return idx - 1


def _local(tag: str) -> str:
    """Zwróć lokalną nazwę taga bez namespace."""
    return tag.rsplit("}", 1)[-1]


def _read_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    try:
        data = zf.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ET.fromstring(data)
    strings: list[str] = []
    for si in root:
        # <si> może mieć wiele <t> (rich text) — sklej
        parts = [t.text or "" for t in si.iter() if _local(t.tag) == "t"]
        strings.append("".join(parts))
    return strings


def _sheet_map(zf: zipfile.ZipFile) -> dict[str, str]:
    """Zmapuj nazwę arkusza -> ścieżka do pliku sheetN.xml."""
    wb = ET.fromstring(zf.read("xl/workbook.xml"))
    rels_raw = zf.read("xl/_rels/workbook.xml.rels")
    rels = ET.fromstring(rels_raw)
    rid_to_target: dict[str, str] = {}
    for rel in rels:
        rid = rel.get("Id")
        target = rel.get("Target")
        if rid and target:
            if not target.startswith("/"):
                target = "xl/" + target.lstrip("./")
            else:
                target = target.lstrip("/")
            rid_to_target[rid] = target

    name_to_path: dict[str, str] = {}
    sheets_el = None
    for child in wb:
        if _local(child.tag) == "sheets":
            sheets_el = child
            break
    if sheets_el is None:
        return name_to_path
    for sheet in sheets_el:
        name = sheet.get("name")
        rid = sheet.get(f"{{{_NS['r']}}}id")
        if name and rid and rid in rid_to_target:
            name_to_path[name] = rid_to_target[rid]
    return name_to_path


def _cell_value(cell: ET.Element, shared: list[str]) -> str:
    """Zwróć wartość komórki jako string (rozwiązuje shared strings / inline)."""
    ctype = cell.get("t")
    if ctype == "inlineStr":
        parts = [t.text or "" for t in cell.iter() if _local(t.tag) == "t"]
        return "".join(parts)
    v_el = None
    for child in cell:
        if _local(child.tag) == "v":
            v_el = child
            break
    if v_el is None or v_el.text is None:
        return ""
    raw = v_el.text
    if ctype == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError):
            return ""
    if ctype == "b":
        return "1" if raw == "1" else "0"
    return raw


def read_sheet_rows(path: str | Path, sheet_name: str) -> list[list[str]]:
    """Zwróć wiersze arkusza jako listy stringów (z wypełnieniem luk kolumn)."""
    path = Path(path)
    with zipfile.ZipFile(path) as zf:
        shared = _read_shared_strings(zf)
        name_to_path = _sheet_map(zf)
        if sheet_name not in name_to_path:
            raise KeyError(
                f"Arkusz '{sheet_name}' nie istnieje. Dostępne: {list(name_to_path)}"
            )
        sheet_xml = zf.read(name_to_path[sheet_name])

    root = ET.fromstring(sheet_xml)
    rows_out: list[list[str]] = []
    for elem in root.iter():
        if _local(elem.tag) != "row":
            continue
        cells: dict[int, str] = {}
        max_col = -1
        for cell in elem:
            if _local(cell.tag) != "c":
                continue
            ref = cell.get("r", "")
            m = _CELL_REF_RE.match(ref)
            col_idx = _col_to_index(m.group(1)) if m else (max_col + 1)
            cells[col_idx] = _cell_value(cell, shared)
            max_col = max(max_col, col_idx)
        row = [cells.get(i, "") for i in range(max_col + 1)] if max_col >= 0 else []
        rows_out.append(row)
    return rows_out


def sheet_names(path: str | Path) -> list[str]:
    with zipfile.ZipFile(Path(path)) as zf:
        return list(_sheet_map(zf).keys())


def read_sheet_records(
    path: str | Path, sheet_name: str, header_row: int = 0
) -> list[dict[str, str]]:
    """Zwróć wiersze arkusza jako listę dictów (klucz = nagłówek kolumny).

    ``header_row`` to indeks wiersza nagłówkowego (0-based) w surowych danych.
    Puste nagłówki dostają nazwę ``col{index}``.
    """
    rows = read_sheet_rows(path, sheet_name)
    if header_row >= len(rows):
        return []
    headers_raw = rows[header_row]
    headers = [
        (h.strip() if h.strip() else f"col{i}") for i, h in enumerate(headers_raw)
    ]
    records: list[dict[str, str]] = []
    for row in rows[header_row + 1:]:
        if not any(cell.strip() for cell in row):
            continue  # pomiń całkowicie puste wiersze
        record = {}
        for i, header in enumerate(headers):
            record[header] = row[i].strip() if i < len(row) else ""
        records.append(record)
    return records
