"""Render a :class:`~doc_files.model.Document` as plain text or as Markdown.

Plain text is what a search reads and what "copy all" should give: the
words, in order, with paragraphs on their own lines, list items marked and
table cells separated by tabs. Markdown keeps the structure a Markdown viewer
can show: headings, emphasis, links, nested lists, tables, and a heading per
page, slide, sheet or chapter.

Both are lossy on purpose — Markdown has no merged cells, for one. A widget
that wants everything reads the model itself.
"""

from __future__ import annotations

import re

from .model import Block, Document, Heading, Image, ListBlock, Paragraph, Run, Section, Table, runs_text

_KIND_NAMES = {"page": "Page", "slide": "Slide", "sheet": "Sheet", "chapter": "Chapter"}


def section_label(s: Section) -> str:
    """``"Slide 3: Results"``, ``"Sheet: Budget"``, ``"Page 12"``…"""
    name = _KIND_NAMES.get(s.kind, s.kind.capitalize())
    label = f"{name} {s.number}" if s.number is not None else name
    if s.title:
        label = f"{label}: {s.title}" if s.number is not None else f"{name}: {s.title}"
    if s.hidden:
        label += " (hidden)"
    return label


# --- plain text --------------------------------------------------------------

def to_text(doc: Document) -> str:
    """The document's words as plain text."""
    out: list[str] = []
    titled = len(doc.sections) > 1 or (doc.sections and doc.sections[0].kind != "body")
    for s in doc.sections:
        if titled:
            if out:
                out.append("")
            out.append(f"== {section_label(s)} ==")
        out.extend(_text_blocks(s.blocks, 0))
        if s.notes:
            out.append("")
            out.append("-- Notes --")
            out.extend(_text_blocks(s.notes, 0))
    return "\n".join(out).rstrip("\n") + ("\n" if out else "")


def _text_blocks(blocks: list[Block], indent: int) -> list[str]:
    pad = "  " * indent
    lines: list[str] = []
    for b in blocks:
        if isinstance(b, (Heading, Paragraph)):
            for line in runs_text(b.runs).split("\n"):
                lines.append(pad + line)
        elif isinstance(b, ListBlock):
            for n, item in enumerate(b.items, 1):
                marker = f"{n}. " if b.ordered else "- "
                sub = _text_blocks(item, 0)
                if not sub:
                    continue
                lines.append(pad + marker + sub[0])
                lines.extend(pad + " " * len(marker) + line for line in sub[1:])
        elif isinstance(b, Table):
            for row in b.rows:
                cells = []
                for c in row:
                    cells.append(" ".join(" ".join(_text_blocks(c.blocks, 0)).split()))
                    cells.extend([""] * (c.colspan - 1))  # keep the columns aligned
                lines.append(pad + "\t".join(cells))
        elif isinstance(b, Image):
            if b.alt:
                lines.append(pad + f"[image: {b.alt}]")
    return lines


# --- Markdown ----------------------------------------------------------------

_MD_SPECIAL = re.compile(r"([\\`*_\[\]<>|])")
_MD_LINE_START = re.compile(r"^(\s*)([#>+\-]|\d+[.)])(\s)")


def _escape(text: str) -> str:
    text = _MD_SPECIAL.sub(r"\\\1", text)
    return _MD_LINE_START.sub(lambda m: f"{m.group(1)}\\{m.group(2)}{m.group(3)}", text)


def _md_runs(runs: list[Run]) -> str:
    out = []
    for r in runs:
        text = _escape(r.text).replace("\n", "  \n")
        stripped = text.strip()
        if not stripped:
            out.append(text)
            continue
        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        inner = stripped
        if r.strike:
            inner = f"~~{inner}~~"
        if r.italic:
            inner = f"*{inner}*"
        if r.bold:
            inner = f"**{inner}**"
        if r.link:
            inner = f"[{inner}]({r.link})"
        out.append(lead + inner + trail)
    return "".join(out)


def to_markdown(doc: Document) -> str:
    """The document as Markdown. A document of several sections gets a
    second-level heading per section, and its own headings are pushed down
    a level beneath them."""
    parts: list[str] = []
    title = doc.meta.get("title")
    first = next((b for s in doc.sections for b in s.blocks), None)
    if title and not (isinstance(first, Heading) and runs_text(first.runs).strip() == title.strip()):
        parts.append(f"# {_escape(title)}")
    sectioned = len(doc.sections) > 1 or (doc.sections and doc.sections[0].kind != "body")
    for s in doc.sections:
        if sectioned:
            parts.append(f"## {_escape(section_label(s))}")
        parts.extend(_md_blocks(s.blocks, shift=2 if sectioned else 0))
        if s.notes:
            parts.append("**Notes**")
            parts.extend(_md_blocks(s.notes, shift=2 if sectioned else 0))
    for w in doc.warnings:
        parts.append(f"> {_escape(w)}")
    return "\n\n".join(p for p in parts if p) + "\n"


def _md_blocks(blocks: list[Block], shift: int = 0, indent: str = "") -> list[str]:
    out: list[str] = []
    for b in blocks:
        if isinstance(b, Heading):
            level = min(6, b.level + shift)
            out.append(f"{indent}{'#' * level} {_md_runs(b.runs)}")
        elif isinstance(b, Paragraph):
            text = _md_runs(b.runs)
            if text.strip():
                out.append(indent + text)
        elif isinstance(b, ListBlock):
            out.append(_md_list(b, indent, shift))
        elif isinstance(b, Table):
            out.append(_md_table(b, indent))
        elif isinstance(b, Image):
            out.append(f"{indent}*[image{': ' + _escape(b.alt) if b.alt else ''}]*")
    return out


def _md_list(b: ListBlock, indent: str, shift: int) -> str:
    lines = []
    for n, item in enumerate(b.items, 1):
        marker = f"{n}. " if b.ordered else "- "
        sub_indent = indent + " " * len(marker)
        sub = _md_blocks(item, shift, sub_indent)
        if not sub:
            continue
        first = sub[0][len(sub_indent):] if sub[0].startswith(sub_indent) else sub[0].lstrip()
        lines.append(indent + marker + first)
        for chunk in sub[1:]:
            lines.append(chunk)
    return "\n".join(lines)


def _cell_md(blocks: list[Block]) -> str:
    text = " ".join(" ".join(_md_blocks(blocks)).split())
    return text.replace("\n", " ") or " "


def _md_table(t: Table, indent: str) -> str:
    """A pipe table. Spanned cells are repeated empty — Markdown has no spans."""
    grid: list[list[str]] = []
    pending: dict[int, int] = {}  # column -> rows still covered by a rowspan
    for row in t.rows:
        line: list[str] = []
        col = 0
        cells = iter(row)
        while True:
            while pending.get(col, 0) > 0:
                pending[col] -= 1
                line.append("")
                col += 1
            cell = next(cells, None)
            if cell is None:
                break
            line.append(_cell_md(cell.blocks))
            if cell.rowspan > 1:
                for c in range(col, col + cell.colspan):
                    pending[c] = cell.rowspan - 1
            line.extend([""] * (cell.colspan - 1))
            col += cell.colspan
        grid.append(line)
    if not grid:
        return ""
    width = max(len(r) for r in grid)
    grid = [r + [""] * (width - len(r)) for r in grid]
    # Markdown needs a header row; without one the first row stands in.
    head, body = grid[0], grid[1:]
    lines = [indent + "| " + " | ".join(head) + " |",
             indent + "|" + "|".join(["---"] * width) + "|"]
    lines += [indent + "| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)
