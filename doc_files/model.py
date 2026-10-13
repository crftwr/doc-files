"""The document model: what a file says, as structure, not as a picture.

Every reader turns its format into the same small tree:

- a :class:`Document` holds :class:`Section` s — the whole body of a word
  processor file, or one page, slide, sheet or chapter each;
- a section holds **blocks**: :class:`Heading`, :class:`Paragraph`,
  :class:`ListBlock`, :class:`Table`, :class:`Image`;
- text is a list of :class:`Run` s, each with its emphasis and link.

The model carries the **meaning** of the layout — heading levels, list
nesting, merged table cells, which slide a note belongs to — and none of its
**geometry**: no positions, sizes, fonts or columns. That boundary is the
point of the library: what comes out can be searched, selected, copied and
wrapped to any width, which a picture of a page cannot.

:meth:`Document.to_dict` and :func:`document_from_dict` convert to and from
plain JSON-able data; ``doc/MODEL_FORMAT.md`` specifies that form, which is
the contract other programs (XeFM, a widget that renders it) rely on.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, Union

#: The version of the dict form (``doc/MODEL_FORMAT.md``).
MODEL_VERSION = 1


@dataclass
class Run:
    """A stretch of text with one set of attributes."""

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    strike: bool = False
    #: A hyperlink target, when the text is one.
    link: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"text": self.text}
        for key in ("bold", "italic", "underline", "strike"):
            if getattr(self, key):
                d[key] = True
        if self.link:
            d["link"] = self.link
        return d


@dataclass
class Heading:
    level: int
    runs: list[Run] = field(default_factory=list)


@dataclass
class Paragraph:
    runs: list[Run] = field(default_factory=list)


@dataclass
class ListBlock:
    """A list. Each item is a list of blocks, so items nest lists."""

    ordered: bool = False
    items: list[list["Block"]] = field(default_factory=list)


@dataclass
class Cell:
    blocks: list["Block"] = field(default_factory=list)
    colspan: int = 1
    rowspan: int = 1


@dataclass
class Table:
    """Rows of cells. A cell covered by another's span is not listed, as in
    HTML. ``header_rows`` counts the rows at the top that are headers."""

    rows: list[list[Cell]] = field(default_factory=list)
    header_rows: int = 0


@dataclass
class Image:
    """A picture in the document: its alternative text, and where it lives
    inside the file (``ref``), when known. The pixels are not carried."""

    alt: str = ""
    ref: Optional[str] = None


Block = Union[Heading, Paragraph, ListBlock, Table, Image]


@dataclass
class Section:
    """One part of a document.

    ``kind`` is ``"body"`` (a word processor document has one), ``"page"``,
    ``"slide"``, ``"sheet"`` or ``"chapter"``. ``title`` names it (a slide's
    title, a sheet's name), ``number`` counts it from 1, ``hidden`` marks a
    hidden slide or sheet.

    Text that is not part of the body sits in its own **layer**, after the
    idea in Docling's model: ``notes`` holds a slide's speaker notes, and
    ``furniture`` what repeats around the body — page headers and footers,
    a slide's footer — which a reader may show apart or leave out.
    """

    kind: str
    blocks: list[Block] = field(default_factory=list)
    title: Optional[str] = None
    number: Optional[int] = None
    hidden: bool = False
    notes: list[Block] = field(default_factory=list)
    furniture: list[Block] = field(default_factory=list)


@dataclass
class Document:
    """What a file says. ``format`` names the reader (``"docx"``, ``"pdf"``…);
    ``meta`` holds what the file declares about itself (``title``,
    ``author``…); ``warnings`` say what could not be read, such as "this PDF
    has no text layer"."""

    format: str
    sections: list[Section] = field(default_factory=list)
    meta: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        """True when nothing at all was found to show."""
        return not any(s.blocks or s.notes for s in self.sections)

    def to_dict(self) -> dict:
        """The JSON-able form, ``doc/MODEL_FORMAT.md``."""
        return {
            "model": "doc-files",
            "version": MODEL_VERSION,
            "format": self.format,
            "meta": dict(self.meta),
            "warnings": list(self.warnings),
            "sections": [_section_dict(s) for s in self.sections],
        }


# --- to and from dicts -------------------------------------------------------

def _runs_dict(runs: list[Run]) -> list[dict]:
    return [r.to_dict() for r in runs]


def block_dict(block: Block) -> dict:
    if isinstance(block, Heading):
        return {"type": "heading", "level": block.level, "runs": _runs_dict(block.runs)}
    if isinstance(block, Paragraph):
        return {"type": "paragraph", "runs": _runs_dict(block.runs)}
    if isinstance(block, ListBlock):
        return {"type": "list", "ordered": block.ordered,
                "items": [[block_dict(b) for b in item] for item in block.items]}
    if isinstance(block, Table):
        rows = []
        for row in block.rows:
            cells = []
            for c in row:
                d: dict[str, Any] = {"blocks": [block_dict(b) for b in c.blocks]}
                if c.colspan != 1:
                    d["colspan"] = c.colspan
                if c.rowspan != 1:
                    d["rowspan"] = c.rowspan
                cells.append(d)
            rows.append(cells)
        d = {"type": "table", "rows": rows}
        if block.header_rows:
            d["header_rows"] = block.header_rows
        return d
    if isinstance(block, Image):
        d = {"type": "image", "alt": block.alt}
        if block.ref:
            d["ref"] = block.ref
        return d
    raise TypeError(f"not a block: {block!r}")


def _section_dict(s: Section) -> dict:
    d: dict[str, Any] = {"kind": s.kind, "blocks": [block_dict(b) for b in s.blocks]}
    if s.title is not None:
        d["title"] = s.title
    if s.number is not None:
        d["number"] = s.number
    if s.hidden:
        d["hidden"] = True
    if s.notes:
        d["notes"] = [block_dict(b) for b in s.notes]
    if s.furniture:
        d["furniture"] = [block_dict(b) for b in s.furniture]
    return d


def _runs(raw) -> list[Run]:
    return [Run(text=str(r.get("text", "")), bold=bool(r.get("bold")), italic=bool(r.get("italic")),
                underline=bool(r.get("underline")), strike=bool(r.get("strike")), link=r.get("link"))
            for r in raw or []]


def block_from_dict(d: dict) -> Block:
    kind = d.get("type")
    if kind == "heading":
        return Heading(int(d.get("level", 1)), _runs(d.get("runs")))
    if kind == "paragraph":
        return Paragraph(_runs(d.get("runs")))
    if kind == "list":
        return ListBlock(bool(d.get("ordered")),
                         [[block_from_dict(b) for b in item] for item in d.get("items", [])])
    if kind == "table":
        rows = [[Cell([block_from_dict(b) for b in c.get("blocks", [])],
                      int(c.get("colspan", 1)), int(c.get("rowspan", 1))) for c in row]
                for row in d.get("rows", [])]
        return Table(rows, int(d.get("header_rows", 0)))
    if kind == "image":
        return Image(str(d.get("alt", "")), d.get("ref"))
    raise ValueError(f"unknown block type {kind!r}")


def document_from_dict(d: dict) -> Document:
    """A :class:`Document` from its dict form. Raises ``ValueError`` for a
    version this library does not read."""
    if d.get("model") != "doc-files" or d.get("version") != MODEL_VERSION:
        raise ValueError("not a doc-files model this version reads")
    sections = [Section(kind=s.get("kind", "body"),
                        blocks=[block_from_dict(b) for b in s.get("blocks", [])],
                        title=s.get("title"), number=s.get("number"),
                        hidden=bool(s.get("hidden")),
                        notes=[block_from_dict(b) for b in s.get("notes", [])],
                        furniture=[block_from_dict(b) for b in s.get("furniture", [])])
                for s in d.get("sections", [])]
    return Document(format=str(d.get("format", "")), sections=sections,
                    meta=dict(d.get("meta", {})), warnings=list(d.get("warnings", [])))


# --- helpers readers share ---------------------------------------------------

def plain(text: str) -> list[Run]:
    """One unstyled run, or none for empty text."""
    return [Run(text)] if text else []


def runs_text(runs: list[Run]) -> str:
    return "".join(r.text for r in runs)


def merge_runs(runs: list[Run]) -> list[Run]:
    """Join neighbouring runs with the same attributes, and drop empty ones —
    readers produce one run per XML element, which splits words."""
    out: list[Run] = []
    for r in runs:
        if not r.text:
            continue
        if out and (out[-1].bold, out[-1].italic, out[-1].underline, out[-1].strike, out[-1].link) == \
                (r.bold, r.italic, r.underline, r.strike, r.link):
            out[-1] = Run(out[-1].text + r.text, r.bold, r.italic, r.underline, r.strike, r.link)
        else:
            out.append(r)
    return out
