"""OpenDocument files — text (``.odt``), spreadsheet (``.ods``) and
presentation (``.odp``) — from ``content.xml``.

- **Text**: ``text:h`` headings (their outline level), paragraphs, lists
  (numbered when their list style numbers that level), tables with spans,
  sections read in place, page headers and footers as ``furniture``.
- **Spreadsheet**: one section per ``table:table``, repeated rows and
  columns expanded only as far as they hold something.
- **Presentation**: one section per ``draw:page``, frames in reading order,
  the title frame naming the slide, ``presentation:notes`` as ``notes``.

Emphasis comes from the automatic styles a span or paragraph names.
"""

from __future__ import annotations

from typing import Optional

from ..model import (Block, Cell, Document, Heading, Image, ListBlock, Paragraph, Run, Section, Table,
                     merge_runs, runs_text)
from .._zipxml import local, member_xml, open_zip

OFFICE = "{urn:oasis:names:tc:opendocument:xmlns:office:1.0}"
TEXT = "{urn:oasis:names:tc:opendocument:xmlns:text:1.0}"
TABLE = "{urn:oasis:names:tc:opendocument:xmlns:table:1.0}"
STYLE = "{urn:oasis:names:tc:opendocument:xmlns:style:1.0}"
FO = "{urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0}"
DRAW = "{urn:oasis:names:tc:opendocument:xmlns:drawing:1.0}"
SVG = "{urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0}"
PRES = "{urn:oasis:names:tc:opendocument:xmlns:presentation:1.0}"
XLINK = "{http://www.w3.org/1999/xlink}"
DC = "{http://purl.org/dc/elements/1.1/}"

#: Repeats expanded at most this far; trailing empty repeats (a sheet's
#: last row repeated to the millionth) are what this stops.
MAX_REPEAT = 1000
MAX_ROWS = 20000
MAX_COLS = 500


def _length(value: Optional[str]) -> float:
    if not value:
        return 0.0
    num = "".join(ch for ch in value if ch.isdigit() or ch in ".-")
    try:
        return float(num)
    except ValueError:
        return 0.0


class _Reader:
    def __init__(self, z, content):
        self.z = z
        self.text_styles: dict[str, dict] = {}
        self.list_ordered: dict[str, dict[int, bool]] = {}
        for root in (member_xml(z, "styles.xml"), content):
            if root is None:
                continue
            self._styles(root)

    def _styles(self, root) -> None:
        for st in root.iter(f"{STYLE}style"):
            props = st.find(f"{STYLE}text-properties")
            if props is None:
                continue
            self.text_styles[st.get(f"{STYLE}name", "")] = {
                "bold": props.get(f"{FO}font-weight") == "bold",
                "italic": props.get(f"{FO}font-style") == "italic",
                "underline": props.get(f"{STYLE}text-underline-style", "none") != "none",
                "strike": props.get(f"{STYLE}text-line-through-style", "none") != "none",
            }
        for ls in root.iter(f"{TEXT}list-style"):
            levels = {}
            for child in ls:
                level = int(child.get(f"{TEXT}level", "1") or 1)
                levels[level] = local(child.tag) == "list-level-style-number"
            self.list_ordered[ls.get(f"{STYLE}name", "")] = levels

    # --- runs -----------------------------------------------------------------

    def runs(self, el, base: Optional[dict] = None, link: Optional[str] = None) -> list[Run]:
        style = dict(base or {})
        own = self.text_styles.get(el.get(f"{TEXT}style-name", ""))
        if own:
            style.update({k: v for k, v in own.items() if v})
        out: list[Run] = []

        def add(text: str) -> None:
            if text:
                out.append(Run(text, style.get("bold", False), style.get("italic", False),
                               style.get("underline", False), style.get("strike", False), link))

        add(el.text or "")
        for child in el:
            tag = local(child.tag)
            if tag == "span":
                out.extend(self.runs(child, style, link))
            elif tag == "a":
                out.extend(self.runs(child, style, child.get(f"{XLINK}href") or link))
            elif tag == "s":
                add(" " * int(child.get(f"{TEXT}c", "1") or 1))
            elif tag == "tab":
                add("\t")
            elif tag == "line-break":
                add("\n")
            elif tag in ("note", "annotation", "bookmark-ref", "soft-page-break"):
                pass
            else:
                out.extend(self.runs(child, style, link))
            add(child.tail or "")
        return merge_runs(out)

    # --- blocks ---------------------------------------------------------------

    def blocks(self, parent, list_style: Optional[str] = None, depth: int = 1) -> list[Block]:
        out: list[Block] = []
        for el in parent:
            tag = local(el.tag)
            if tag == "h":
                runs = self.runs(el)
                if runs_text(runs).strip():
                    level = int(el.get(f"{TEXT}outline-level", "1") or 1)
                    out.append(Heading(min(max(level, 1), 6), runs))
            elif tag == "p":
                runs = self.runs(el)
                if runs_text(runs).strip():
                    out.append(Paragraph(runs))
                for frame in el.iter(f"{DRAW}frame"):
                    img = self._image(frame)
                    if img is not None:
                        out.append(img)
            elif tag == "list":
                out.append(self.list(el, list_style, depth))
            elif tag == "table":
                out.append(self.table(el))
            elif tag in ("section", "index-body", "table-of-content", "illustration-index"):
                out.extend(self.blocks(el, list_style, depth))
            elif tag == "frame":
                img = self._image(el)
                if img is not None:
                    out.append(img)
                box = el.find(f"{DRAW}text-box")
                if box is not None:
                    out.extend(self.blocks(box))
        return out

    def _image(self, frame) -> Optional[Image]:
        if frame.find(f"{DRAW}image") is None:
            return None
        title = frame.find(f"{SVG}title")
        desc = frame.find(f"{SVG}desc")
        alt = (desc.text if desc is not None and desc.text else
               title.text if title is not None and title.text else frame.get(f"{DRAW}name", ""))
        return Image(alt=alt or "")

    def list(self, el, inherited: Optional[str], depth: int) -> ListBlock:
        style = el.get(f"{TEXT}style-name") or inherited
        ordered = self.list_ordered.get(style or "", {}).get(depth, False)
        block = ListBlock(ordered=ordered)
        for item in el:
            if local(item.tag) not in ("list-item", "list-header"):
                continue
            block.items.append(self.blocks(item, style, depth + 1))
        return block

    def table(self, el) -> Table:
        rows: list[list[Cell]] = []
        header_rows = 0
        for row_el, is_header in self._rows(el):
            row: list[Cell] = []
            for cell_el in row_el:
                tag = local(cell_el.tag)
                repeat = min(int(cell_el.get(f"{TABLE}number-columns-repeated", "1") or 1), MAX_REPEAT)
                if tag == "covered-table-cell":
                    continue
                if tag != "table-cell":
                    continue
                blocks = self.blocks(cell_el)
                if not blocks and repeat > 1:
                    repeat = 1 if len(row) < MAX_COLS else 0
                for _ in range(repeat):
                    if len(row) >= MAX_COLS:
                        break
                    row.append(Cell(list(blocks),
                                    colspan=int(cell_el.get(f"{TABLE}number-columns-spanned", "1") or 1),
                                    rowspan=int(cell_el.get(f"{TABLE}number-rows-spanned", "1") or 1)))
            while row and not row[-1].blocks and row[-1].colspan == 1 and row[-1].rowspan == 1:
                row.pop()
            if is_header:
                header_rows += 1
            rows.append(row)
            if len(rows) >= MAX_ROWS:
                break
        while rows and not rows[-1]:
            rows.pop()
        return Table(rows, header_rows)

    def _rows(self, el, header: bool = False):
        for child in el:
            tag = local(child.tag)
            if tag == "table-row":
                repeat = int(child.get(f"{TABLE}number-rows-repeated", "1") or 1)
                has_content = any(c.text or len(c) for c in child)
                for _ in range(min(repeat, MAX_REPEAT) if has_content else 1):
                    yield child, header
            elif tag == "table-header-rows":
                yield from self._rows(child, True)
            elif tag in ("table-rows", "table-row-group"):
                yield from self._rows(child, header)

    def furniture(self) -> list[Block]:
        root = member_xml(self.z, "styles.xml")
        out: list[Block] = []
        if root is None:
            return out
        for tag in ("header", "footer"):
            for el in root.iter(f"{STYLE}{tag}"):
                out.extend(self.blocks(el))
        return out


def _meta(z) -> dict[str, str]:
    root = member_xml(z, "meta.xml")
    meta: dict[str, str] = {}
    if root is None:
        return meta
    for el in root.iter():
        name, text = local(el.tag), (el.text or "").strip()
        if not text:
            continue
        if name == "title" and el.tag.startswith(DC):
            meta["title"] = text
        elif name in ("creator", "initial-creator") and "author" not in meta:
            meta["author"] = text
    return meta


def read(data: bytes, password: Optional[str] = None) -> Document:
    z = open_zip(data)
    content = member_xml(z, "content.xml")
    doc = Document(format="odf", meta=_meta(z))
    if content is None:
        doc.warnings.append("no content.xml: not an OpenDocument file")
        return doc
    body = content.find(f"{OFFICE}body")
    reader = _Reader(z, content)
    if body is None:
        return doc
    text = body.find(f"{OFFICE}text")
    sheet = body.find(f"{OFFICE}spreadsheet")
    pres = body.find(f"{OFFICE}presentation")
    if text is not None:
        doc.format = "odt"
        doc.sections.append(Section("body", reader.blocks(text), furniture=reader.furniture()))
    elif sheet is not None:
        doc.format = "ods"
        for n, t in enumerate(sheet.findall(f"{TABLE}table"), 1):
            table = reader.table(t)
            doc.sections.append(Section("sheet", [table] if table.rows else [],
                                        title=t.get(f"{TABLE}name"), number=n))
    elif pres is not None:
        doc.format = "odp"
        for n, page in enumerate(pres.findall(f"{DRAW}page"), 1):
            section = Section("slide", number=n)
            frames = [f for f in page if local(f.tag) in ("frame", "custom-shape", "g")]
            frames.sort(key=lambda f: (_length(f.get(f"{SVG}y")), _length(f.get(f"{SVG}x"))))
            for frame in frames:
                cls = frame.get(f"{PRES}class")
                box = frame.find(f"{DRAW}text-box")
                blocks = reader.blocks(box if box is not None else frame)
                if cls == "title" and section.title is None:
                    section.title = " ".join(runs_text(b.runs) for b in blocks
                                             if isinstance(b, (Paragraph, Heading))).strip() or None
                    continue
                if cls in ("footer", "date-time", "page-number", "header"):
                    section.furniture.extend(blocks)
                    continue
                if cls == "outline":
                    blocks = [b if isinstance(b, ListBlock) else ListBlock(items=[[b]]) for b in blocks]
                section.blocks.extend(blocks)
            notes = page.find(f"{PRES}notes")
            if notes is not None:
                for frame in notes.iter(f"{DRAW}frame"):
                    if frame.get(f"{PRES}class") == "notes":
                        box = frame.find(f"{DRAW}text-box")
                        if box is not None:
                            section.notes.extend(reader.blocks(box))
            doc.sections.append(section)
    return doc
