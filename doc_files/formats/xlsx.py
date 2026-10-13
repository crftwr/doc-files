"""Excel workbooks (``.xlsx``, Office Open XML): one section per sheet.

Each sheet becomes a table of the values its cells hold — the cached result
for a formula, the shared or inline string for text — with merged ranges
kept as spans. Number formats are not applied: a date shows as the serial
number Excel stores, which says what the cell holds if not how Excel would
draw it. Very large sheets are cut at :data:`MAX_ROWS` × :data:`MAX_COLS`,
with a warning.
"""

from __future__ import annotations

import re
from typing import Optional

from ..model import Cell, Document, Paragraph, Section, Table, plain
from .._zipxml import member_xml, open_zip
from .ooxml import core_meta, relationships, resolve

S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

MAX_ROWS = 20000
MAX_COLS = 500

_REF = re.compile(r"^([A-Z]+)(\d+)$")


def _col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n - 1


def _ref(ref: str) -> Optional[tuple[int, int]]:
    m = _REF.match(ref or "")
    if not m:
        return None
    return int(m.group(2)) - 1, _col_index(m.group(1))


def _shared_strings(z) -> list[str]:
    root = member_xml(z, "xl/sharedStrings.xml")
    if root is None:
        return []
    out = []
    for si in root.findall(f"{S}si"):
        out.append("".join(t.text or "" for t in si.iter(f"{S}t")))
    return out


def _number(text: str) -> str:
    """A stored number as written, without a float's noise (``3.0`` → ``3``)."""
    try:
        value = float(text)
    except ValueError:
        return text
    if value.is_integer() and abs(value) < 1e15:
        return str(int(value))
    return repr(value) if "e" not in text.lower() else text


def _sheet(z, path: str, strings: list[str], warnings: list[str], name: str) -> Table:
    root = member_xml(z, path)
    if root is None:
        return Table()
    values: dict[tuple[int, int], str] = {}
    max_r = max_c = -1
    cut = False
    for row in root.iter(f"{S}row"):
        for c in row.findall(f"{S}c"):
            pos = _ref(c.get("r", ""))
            if pos is None:
                continue
            r, col = pos
            if r >= MAX_ROWS or col >= MAX_COLS:
                cut = True
                continue
            kind = c.get("t", "n")
            v = c.find(f"{S}v")
            if kind == "inlineStr":
                is_ = c.find(f"{S}is")
                text = "".join(t.text or "" for t in is_.iter(f"{S}t")) if is_ is not None else ""
            elif v is None or v.text is None:
                continue
            elif kind == "s":
                idx = int(v.text) if v.text.isdigit() else -1
                text = strings[idx] if 0 <= idx < len(strings) else ""
            elif kind == "b":
                text = "TRUE" if v.text == "1" else "FALSE"
            elif kind in ("str", "e"):
                text = v.text
            else:
                text = _number(v.text)
            if text == "":
                continue
            values[(r, col)] = text
            max_r, max_c = max(max_r, r), max(max_c, col)
    if cut:
        warnings.append(f"sheet {name!r} cut at {MAX_ROWS} rows × {MAX_COLS} columns")
    # Merged ranges: the top-left cell spans; the rest are covered.
    spans: dict[tuple[int, int], tuple[int, int]] = {}
    covered: set[tuple[int, int]] = set()
    for mc in root.iter(f"{S}mergeCell"):
        a, _sep, b = (mc.get("ref") or "").partition(":")
        p, q = _ref(a), _ref(b)
        if p is None or q is None:
            continue
        rows, cols = q[0] - p[0] + 1, q[1] - p[1] + 1
        if p[0] > max_r and p[1] > max_c:
            continue
        spans[p] = (rows, cols)
        for rr in range(p[0], q[0] + 1):
            for cc in range(p[1], q[1] + 1):
                if (rr, cc) != p:
                    covered.add((rr, cc))
        max_r, max_c = max(max_r, min(q[0], MAX_ROWS - 1)), max(max_c, min(q[1], MAX_COLS - 1))
    rows_out: list[list[Cell]] = []
    for r in range(max_r + 1):
        row: list[Cell] = []
        for col in range(max_c + 1):
            if (r, col) in covered:
                continue
            text = values.get((r, col), "")
            rs, cs = spans.get((r, col), (1, 1))
            row.append(Cell([Paragraph(plain(text))] if text else [], colspan=cs, rowspan=rs))
        rows_out.append(row)
    return Table(rows_out)


def read(data: bytes, password: Optional[str] = None) -> Document:
    z = open_zip(data)
    doc = Document(format="xlsx", meta=core_meta(z))
    wb = member_xml(z, "xl/workbook.xml")
    if wb is None:
        doc.warnings.append("no xl/workbook.xml: not an Excel workbook")
        return doc
    rels = relationships(z, "xl/workbook.xml")
    strings = _shared_strings(z)
    for n, sheet in enumerate(wb.iter(f"{S}sheet"), 1):
        name = sheet.get("name", f"Sheet{n}")
        rel = rels.get(sheet.get(f"{R}id", ""))
        if rel is None:
            continue
        table = _sheet(z, resolve("xl/workbook.xml", rel["target"]), strings, doc.warnings, name)
        blocks = [table] if table.rows else []
        doc.sections.append(Section("sheet", blocks, title=name, number=n,
                                    hidden=sheet.get("state", "visible") != "visible"))
    return doc
