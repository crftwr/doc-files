"""PowerPoint presentations (``.pptx``, Office Open XML): one section per
slide, in the presentation's order.

A slide's meaning is partly where things sit, so position is used — but only
to decide **reading order** (top to bottom, then left to right); no
coordinate reaches the model. Beyond that, the structure is the file's own:

- the title placeholder names the section;
- body placeholders are lists, with their paragraph levels as nesting;
  other text boxes are paragraphs unless they carry bullets;
- grouped shapes are read in place; tables keep their merged cells; a
  picture keeps its alternative text;
- date, footer and slide-number placeholders go to ``furniture``;
- the speaker notes go to ``notes``;
- a hidden slide is marked.
"""

from __future__ import annotations

from typing import Optional

from ..model import Block, Cell, Document, Image, ListBlock, Paragraph, Run, Section, Table, merge_runs, runs_text
from .._zipxml import local, member_xml, open_zip
from .ooxml import core_meta, relationships, resolve

P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

_FURNITURE = {"dt", "ftr", "sldNum", "hdr"}
_TITLES = {"title", "ctrTitle"}


def _position(el) -> tuple[int, int]:
    off = el.find(f".//{A}off")
    if off is None:
        return (0, 0)
    try:
        return int(off.get("y", 0)), int(off.get("x", 0))
    except ValueError:
        return (0, 0)


class _Slide:
    def __init__(self, z, part: str):
        self.z = z
        self.rels = relationships(z, part)

    def _runs(self, para) -> list[Run]:
        out: list[Run] = []
        for el in para:
            tag = local(el.tag)
            if tag in ("r", "fld"):
                rpr = el.find(f"{A}rPr")
                t = el.find(f"{A}t")
                text = t.text if t is not None and t.text else ""
                if not text:
                    continue
                bold = italic = underline = strike = False
                link = None
                if rpr is not None:
                    bold = rpr.get("b") in ("1", "true")
                    italic = rpr.get("i") in ("1", "true")
                    underline = rpr.get("u", "none") != "none"
                    strike = rpr.get("strike", "noStrike") != "noStrike"
                    h = rpr.find(f"{A}hlinkClick")
                    if h is not None:
                        rel = self.rels.get(h.get(f"{R}id", ""))
                        link = rel["target"] if rel and rel.get("external") else None
                out.append(Run(text, bold, italic, underline, strike, link))
            elif tag == "br":
                out.append(Run("\n"))
        return merge_runs(out)

    def text_body(self, body, as_list: bool) -> list[Block]:
        """The paragraphs of a text body: a list (nested by ``lvl``) when the
        shape is a bullet body or the paragraphs carry bullets, else
        paragraphs."""
        paras = []
        for p in body.findall(f"{A}p"):
            runs = self._runs(p)
            if not runs_text(runs).strip():
                continue
            ppr = p.find(f"{A}pPr")
            lvl = int(ppr.get("lvl", 0)) if ppr is not None and str(ppr.get("lvl", "0")).isdigit() else 0
            bullet = None
            if ppr is not None:
                if ppr.find(f"{A}buNone") is not None:
                    bullet = False
                elif ppr.find(f"{A}buAutoNum") is not None:
                    bullet = "ordered"
                elif ppr.find(f"{A}buChar") is not None:
                    bullet = True
            paras.append((runs, lvl, bullet))
        out: list[Block] = []
        stack: list[tuple[ListBlock, int]] = []
        for runs, lvl, bullet in paras:
            is_item = bullet not in (False, None) or (as_list and bullet is not False)
            if not is_item:
                stack.clear()
                out.append(Paragraph(runs))
                continue
            while stack and stack[-1][1] > lvl:
                stack.pop()
            item: list[Block] = [Paragraph(runs)]
            if stack and stack[-1][1] == lvl:
                stack[-1][0].items.append(item)
                continue
            new = ListBlock(ordered=bullet == "ordered", items=[item])
            if stack and stack[-1][0].items:
                stack[-1][0].items[-1].append(new)
            else:
                out.append(new)
            stack.append((new, lvl))
        return out

    def table(self, tbl) -> Table:
        rows = []
        for tr in tbl.findall(f"{A}tr"):
            row = []
            for tc in tr.findall(f"{A}tc"):
                if tc.get("hMerge") in ("1", "true") or tc.get("vMerge") in ("1", "true"):
                    continue
                body = tc.find(f"{A}txBody")
                blocks = self.text_body(body, False) if body is not None else []
                row.append(Cell(blocks, colspan=int(tc.get("gridSpan", 1) or 1),
                                rowspan=int(tc.get("rowSpan", 1) or 1)))
            rows.append(row)
        first = tbl.find(f"{A}tblPr")
        header = 1 if first is not None and first.get("firstRow") in ("1", "true") else 0
        return Table(rows, header)

    def shapes(self, tree, section: Section) -> None:
        """Read the shapes of ``tree`` into ``section``, in reading order."""
        items = []
        for el in tree:
            tag = local(el.tag)
            if tag in ("sp", "grpSp", "graphicFrame", "pic", "cxnSp"):
                items.append((_position(el), el))
        items.sort(key=lambda pe: pe[0])
        for _pos, el in items:
            tag = local(el.tag)
            if tag == "grpSp":
                self.shapes(el, section)
            elif tag == "sp":
                self._shape(el, section)
            elif tag == "graphicFrame":
                tbl = el.find(f".//{A}tbl")
                if tbl is not None:
                    section.blocks.append(self.table(tbl))
            elif tag == "pic":
                c_nv = el.find(f".//{P}cNvPr")
                alt = (c_nv.get("descr") or c_nv.get("title") or "") if c_nv is not None else ""
                section.blocks.append(Image(alt=alt))

    def _shape(self, sp, section: Section) -> None:
        ph = sp.find(f"{P}nvSpPr/{P}nvPr/{P}ph")
        kind = ph.get("type", "body") if ph is not None else None
        body = sp.find(f"{P}txBody")
        if body is None:
            return
        if kind in _TITLES:
            title = " ".join(runs_text(self._runs(p)) for p in body.findall(f"{A}p")).strip()
            if title and section.title is None:
                section.title = " ".join(title.split())
                return
        if kind in _FURNITURE:
            section.furniture.extend(self.text_body(body, False))
            return
        as_list = kind in ("body", "obj") and ph is not None
        section.blocks.extend(self.text_body(body, as_list))


def _notes_blocks(z, slide_part: str, rels: dict) -> list[Block]:
    for rel in rels.values():
        if not rel["type"].endswith("/notesSlide"):
            continue
        part = resolve(slide_part, rel["target"])
        root = member_xml(z, part)
        if root is None:
            return []
        reader = _Slide(z, part)
        out: list[Block] = []
        for sp in root.iter(f"{P}sp"):
            ph = sp.find(f"{P}nvSpPr/{P}nvPr/{P}ph")
            kind = ph.get("type", "body") if ph is not None else None
            if kind != "body":
                continue
            body = sp.find(f"{P}txBody")
            if body is not None:
                out.extend(reader.text_body(body, False))
        return out
    return []


def read(data: bytes, password: Optional[str] = None) -> Document:
    z = open_zip(data)
    doc = Document(format="pptx", meta=core_meta(z))
    pres = member_xml(z, "ppt/presentation.xml")
    if pres is None:
        doc.warnings.append("no ppt/presentation.xml: not a PowerPoint file")
        return doc
    rels = relationships(z, "ppt/presentation.xml")
    for n, sld in enumerate(pres.iter(f"{P}sldId"), 1):
        rel = rels.get(sld.get(f"{R}id", ""))
        if rel is None:
            continue
        part = resolve("ppt/presentation.xml", rel["target"])
        root = member_xml(z, part)
        if root is None:
            continue
        reader = _Slide(z, part)
        section = Section("slide", number=n, hidden=root.get("show") in ("0", "false"))
        tree = root.find(f"{P}cSld/{P}spTree")
        if tree is not None:
            reader.shapes(tree, section)
        section.notes = _notes_blocks(z, part, reader.rels)
        doc.sections.append(section)
    return doc
