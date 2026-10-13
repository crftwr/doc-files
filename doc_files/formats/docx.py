"""Word documents (``.docx``, Office Open XML): ``word/document.xml``.

Structure comes from the file's own markup, not from how it looks:

- a heading is a paragraph whose style has an outline level (the built-in
  "Heading 1"…"Heading 9", and "Title");
- a list item is a paragraph with numbering (``w:numPr``); its level gives
  the nesting, and the numbering definition says bullet or number;
- a table keeps its merged cells: ``w:gridSpan`` across, ``w:vMerge`` down;
- headers and footers go to the section's ``furniture`` layer.
"""

from __future__ import annotations

import posixpath
import re
from typing import Optional

from ..model import (Block, Cell, Document, Heading, Image, ListBlock, Paragraph, Run, Section, Table,
                     merge_runs)
from .._zipxml import local, member_xml, open_zip
from .ooxml import core_meta, relationships

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"

_HEADING_NAME = re.compile(r"^heading\s*(\d)$", re.I)
#: Word's built-in list styles carry their depth in the name: "List Bullet 2"
#: is a second-level bullet, with its own numbering and no ``w:ilvl``.
_LIST_STYLE_LEVEL = re.compile(r"^list(?:\s+(?:bullet|number|continue|paragraph))?\s+(\d)$", re.I)


def _on(el) -> bool:
    """A toggle property (``<w:b/>``, ``<w:b w:val="0"/>``)."""
    if el is None:
        return False
    return el.get(f"{W}val", "true").lower() not in ("0", "false", "off", "none")


class _Reader:
    def __init__(self, z):
        self.z = z
        self.rels = relationships(z, "word/document.xml")
        self.heading_level: dict[str, int] = {}
        self._styles()
        self.ordered: dict[tuple[str, int], bool] = {}
        self._numbering()

    def _styles(self) -> None:
        """Heading levels and list numbering per paragraph style, following
        ``basedOn`` — Word's "List Bullet" puts its numbering on the style,
        not on the paragraph."""
        self.style_num: dict[str, tuple[str, int]] = {}
        self.style_depth: dict[str, int] = {}
        root = member_xml(self.z, "word/styles.xml")
        if root is None:
            return
        based: dict[str, str] = {}
        own_num: dict[str, tuple[str, int]] = {}
        for st in root.iter(f"{W}style"):
            sid = st.get(f"{W}styleId") or ""
            b = st.find(f"{W}basedOn")
            if b is not None:
                based[sid] = b.get(f"{W}val", "")
            num = st.find(f"{W}pPr/{W}numPr")
            if num is not None:
                num_id = num.find(f"{W}numId")
                ilvl = num.find(f"{W}ilvl")
                if num_id is not None:
                    own_num[sid] = (num_id.get(f"{W}val", ""),
                                    int(ilvl.get(f"{W}val", "0")) if ilvl is not None else 0)
        for sid in list(based) + list(own_num):
            seen, cur = set(), sid
            while cur and cur not in own_num and cur not in seen:
                seen.add(cur)
                cur = based.get(cur, "")
            if cur in own_num:
                self.style_num[sid] = own_num[cur]
        for st in root.iter(f"{W}style"):
            sid = st.get(f"{W}styleId")
            name_el = st.find(f"{W}name")
            name = name_el.get(f"{W}val", "") if name_el is not None else ""
            depth = _LIST_STYLE_LEVEL.match(name)
            if sid and depth:
                self.style_depth[sid] = int(depth.group(1)) - 1
            level = None
            outline = st.find(f"{W}pPr/{W}outlineLvl")
            if outline is not None and outline.get(f"{W}val", "").isdigit():
                level = int(outline.get(f"{W}val")) + 1
            m = _HEADING_NAME.match(name)
            if m:
                level = int(m.group(1))
            if name.lower() == "title":
                level = 1
            if sid and level and level <= 9:
                self.heading_level[sid] = min(level, 6)

    def _numbering(self) -> None:
        root = member_xml(self.z, "word/numbering.xml")
        if root is None:
            return
        abstract: dict[str, dict[int, bool]] = {}
        for an in root.iter(f"{W}abstractNum"):
            levels = {}
            for lvl in an.findall(f"{W}lvl"):
                fmt = lvl.find(f"{W}numFmt")
                fmt_val = fmt.get(f"{W}val", "bullet") if fmt is not None else "bullet"
                levels[int(lvl.get(f"{W}ilvl", "0"))] = fmt_val not in ("bullet", "none")
            abstract[an.get(f"{W}abstractNumId", "")] = levels
        for num in root.iter(f"{W}num"):
            ref = num.find(f"{W}abstractNumId")
            if ref is None:
                continue
            for lvl, ordered in abstract.get(ref.get(f"{W}val", ""), {}).items():
                self.ordered[(num.get(f"{W}numId", ""), lvl)] = ordered

    # --- runs -----------------------------------------------------------------

    def runs(self, p) -> list[Run]:
        out: list[Run] = []
        for child in p:
            tag = local(child.tag)
            if tag == "r":
                out.extend(self._run(child, None))
            elif tag == "hyperlink":
                link = self.rels.get(child.get(f"{R}id", ""), {}).get("target")
                anchor = child.get(f"{W}anchor")
                link = link or (f"#{anchor}" if anchor else None)
                for r in child.iter(f"{W}r"):
                    out.extend(self._run(r, link))
            elif tag in ("ins", "smartTag", "sdt", "fldSimple"):
                for r in child.iter(f"{W}r"):
                    out.extend(self._run(r, None))
        return merge_runs(out)

    def _run(self, r, link: Optional[str]) -> list[Run]:
        rpr = r.find(f"{W}rPr")
        bold = italic = underline = strike = False
        if rpr is not None:
            bold = _on(rpr.find(f"{W}b"))
            italic = _on(rpr.find(f"{W}i"))
            u = rpr.find(f"{W}u")
            underline = u is not None and u.get(f"{W}val", "single") != "none"
            strike = _on(rpr.find(f"{W}strike")) or _on(rpr.find(f"{W}dstrike"))
        parts = []
        for el in r:
            tag = local(el.tag)
            if tag == "t":
                parts.append(el.text or "")
            elif tag == "tab":
                parts.append("\t")
            elif tag in ("br", "cr"):
                parts.append("\n")
            elif tag == "noBreakHyphen":
                parts.append("-")
        text = "".join(parts)
        return [Run(text, bold, italic, underline, strike, link)] if text else []

    def images(self, p) -> list[Image]:
        out = []
        for doc_pr in p.iter(f"{WP}docPr"):
            alt = doc_pr.get("descr") or doc_pr.get("title") or ""
            out.append(Image(alt=alt))
        return out

    # --- blocks ---------------------------------------------------------------

    def blocks(self, parent) -> list[Block]:
        out: list[Block] = []
        list_stack: list[tuple[ListBlock, int]] = []

        def close_lists() -> None:
            list_stack.clear()

        for child in parent:
            tag = local(child.tag)
            if tag == "sdt":
                content = child.find(f"{W}sdtContent")
                if content is not None:
                    close_lists()
                    out.extend(self.blocks(content))
                continue
            if tag == "tbl":
                close_lists()
                out.append(self.table(child))
                continue
            if tag != "p":
                continue
            ppr = child.find(f"{W}pPr")
            style = ppr.find(f"{W}pStyle").get(f"{W}val") if ppr is not None and \
                ppr.find(f"{W}pStyle") is not None else None
            num = ppr.find(f"{W}numPr") if ppr is not None else None
            runs = self.runs(child)
            images = self.images(child)
            level = self.heading_level.get(style or "")
            outline = ppr.find(f"{W}outlineLvl") if ppr is not None else None
            if outline is not None and outline.get(f"{W}val", "").isdigit():
                level = min(int(outline.get(f"{W}val")) + 1, 6)
            if level and runs:
                close_lists()
                out.append(Heading(level, runs))
                out.extend(images)
                continue
            numbering = None
            if num is not None:
                ilvl_el, num_id_el = num.find(f"{W}ilvl"), num.find(f"{W}numId")
                style_num = self.style_num.get(style or "", ("", 0))
                numbering = (num_id_el.get(f"{W}val", "") if num_id_el is not None else style_num[0],
                             int(ilvl_el.get(f"{W}val", "0")) if ilvl_el is not None else style_num[1])
            elif style in self.style_num:
                numbering = self.style_num[style]
            if numbering is not None and (runs or images):
                num_id, ilvl = numbering
                if num_id and num_id != "0":
                    ordered = self.ordered.get((num_id, ilvl), False)
                    ilvl = max(ilvl, self.style_depth.get(style or "", 0))
                    item: list[Block] = [Paragraph(runs)] if runs else []
                    item.extend(images)
                    self._add_item(out, list_stack, ilvl, ordered, item)
                    continue
            close_lists()
            if runs:
                out.append(Paragraph(runs))
            out.extend(images)
        return out

    @staticmethod
    def _add_item(out: list[Block], stack: list[tuple[ListBlock, int]], level: int,
                  ordered: bool, item: list[Block]) -> None:
        while stack and stack[-1][1] > level:
            stack.pop()
        if stack and stack[-1][1] == level:
            if stack[-1][0].ordered == ordered:
                stack[-1][0].items.append(item)
                return
            # A bullet list followed by a numbered one: two lists.
            stack.pop()
        new = ListBlock(ordered=ordered, items=[item])
        if stack and stack[-1][0].items:
            stack[-1][0].items[-1].append(new)
        else:
            out.append(new)
        stack.append((new, level))

    def table(self, tbl) -> Table:
        rows: list[list[Cell]] = []
        header_rows = 0
        counting_headers = True
        # Grid column -> the cell a vertical merge started in, to grow its rowspan.
        open_merge: dict[int, Cell] = {}
        for tr in tbl.findall(f"{W}tr"):
            trpr = tr.find(f"{W}trPr")
            is_header = trpr is not None and _on(trpr.find(f"{W}tblHeader"))
            if counting_headers and is_header:
                header_rows += 1
            else:
                counting_headers = False
            row: list[Cell] = []
            col = 0
            for tc in tr.findall(f"{W}tc"):
                tcpr = tc.find(f"{W}tcPr")
                span = 1
                vmerge = None
                if tcpr is not None:
                    gs = tcpr.find(f"{W}gridSpan")
                    if gs is not None and gs.get(f"{W}val", "1").isdigit():
                        span = max(1, int(gs.get(f"{W}val")))
                    vm = tcpr.find(f"{W}vMerge")
                    if vm is not None:
                        vmerge = vm.get(f"{W}val", "continue")
                if vmerge == "continue" and col in open_merge:
                    open_merge[col].rowspan += 1
                    col += span
                    continue
                cell = Cell(self.blocks(tc), colspan=span)
                if vmerge == "restart":
                    open_merge[col] = cell
                else:
                    open_merge.pop(col, None)
                row.append(cell)
                col += span
            rows.append(row)
        return Table(rows, header_rows)

    def furniture(self) -> list[Block]:
        out: list[Block] = []
        seen: set[str] = set()
        for rid, rel in self.rels.items():
            kind = rel.get("type", "")
            if not (kind.endswith("/header") or kind.endswith("/footer")):
                continue
            path = posixpath.normpath(posixpath.join("word", rel["target"]))
            root = member_xml(self.z, path)
            if root is None:
                continue
            for b in self.blocks(root):
                key = repr(b)
                if key not in seen:
                    seen.add(key)
                    out.append(b)
        return out


def read(data: bytes, password: Optional[str] = None) -> Document:
    z = open_zip(data)
    root = member_xml(z, "word/document.xml")
    doc = Document(format="docx", meta=core_meta(z))
    if root is None:
        doc.warnings.append("no word/document.xml: not a Word document")
        return doc
    reader = _Reader(z)
    body = root.find(f"{W}body")
    blocks = reader.blocks(body) if body is not None else []
    doc.sections.append(Section("body", blocks, furniture=reader.furniture()))
    return doc
