"""HTML (and XHTML) to blocks — what an EPUB chapter is made of.

Built on the standard library's tolerant :class:`html.parser.HTMLParser`, so
markup that is not well-formed still reads. Headings, paragraphs, lists,
tables (with ``colspan`` / ``rowspan``), images (their ``alt``), emphasis and
links become the model's blocks and runs; scripts, styles and the document
head are skipped. Anything else contributes its text to the block around it.
"""

from __future__ import annotations

from html.parser import HTMLParser
from typing import Optional

from ..model import Block, Cell, Heading, Image, ListBlock, Paragraph, Run, Table, merge_runs, runs_text

_BLOCK = {"p", "div", "section", "article", "aside", "header", "footer", "nav", "main",
          "blockquote", "figure", "figcaption", "address", "pre", "dd", "dt", "body", "hr"}
_SKIP = {"script", "style", "head", "title", "template", "noscript", "svg", "math"}
_EMPHASIS = {"b": "bold", "strong": "bold", "i": "italic", "em": "italic", "cite": "italic",
             "u": "underline", "ins": "underline", "s": "strike", "strike": "strike", "del": "strike"}


class _Container:
    """Where blocks are being collected: the body, a list item, a cell."""

    def __init__(self):
        self.blocks: list[Block] = []


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Container()
        self.containers: list[_Container] = [self.root]
        self.runs: list[Run] = []
        self.heading: Optional[int] = None
        self.style: list[dict] = [{}]
        self.links: list[Optional[str]] = [None]
        self.skip = 0
        self.pre = 0
        # Lists and tables being built, innermost last.
        self.lists: list[ListBlock] = []
        self.tables: list[tuple[Table, list[Cell]]] = []
        self.title: Optional[str] = None

    # --- text -----------------------------------------------------------------

    def _flush(self) -> None:
        runs = merge_runs(self.runs)
        self.runs = []
        text = runs_text(runs)
        if not text.strip():
            return
        if not self.pre:
            runs = _collapse(runs)
        if self.heading:
            self.containers[-1].blocks.append(Heading(self.heading, runs))
            if self.title is None:
                self.title = " ".join(runs_text(runs).split())
        else:
            self.containers[-1].blocks.append(Paragraph(runs))

    def handle_data(self, data: str) -> None:
        if self.skip:
            return
        st = self.style[-1]
        self.runs.append(Run(data, st.get("bold", False), st.get("italic", False),
                             st.get("underline", False), st.get("strike", False), self.links[-1]))

    # --- tags -----------------------------------------------------------------

    def handle_starttag(self, tag: str, attrs) -> None:
        a = dict(attrs)
        if tag in _SKIP:
            self.skip += 1
            return
        if self.skip:
            return
        if tag in _EMPHASIS:
            self.style.append({**self.style[-1], _EMPHASIS[tag]: True})
        elif tag == "a":
            self.links.append(a.get("href") or self.links[-1])
        elif tag == "br":
            self.runs.append(Run("\n"))
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush()
            self.heading = int(tag[1])
        elif tag in _BLOCK:
            self._flush()
            if tag == "pre":
                self.pre += 1
        elif tag in ("ul", "ol"):
            self._flush()
            block = ListBlock(ordered=tag == "ol")
            self.containers[-1].blocks.append(block)
            self.lists.append(block)
        elif tag == "li":
            self._flush()
            item = _Container()
            if self.lists:
                self.lists[-1].items.append(item.blocks)
            else:
                lst = ListBlock()
                self.containers[-1].blocks.append(lst)
                lst.items.append(item.blocks)
            self.containers.append(item)
        elif tag == "table":
            self._flush()
            table = Table()
            self.containers[-1].blocks.append(table)
            self.tables.append((table, []))
        elif tag == "tr":
            self._flush()
            if self.tables:
                table, _row = self.tables[-1]
                row: list[Cell] = []
                table.rows.append(row)
                self.tables[-1] = (table, row)
        elif tag in ("td", "th"):
            self._flush()
            if self.tables:
                table, row = self.tables[-1]
                if not table.rows:
                    table.rows.append(row)
                cell = Cell(colspan=_int(a.get("colspan")), rowspan=_int(a.get("rowspan")))
                row.append(cell)
                if tag == "th" and len(table.rows) == 1:
                    table.header_rows = 1
                holder = _Container()
                holder.blocks = cell.blocks
                self.containers.append(holder)
        elif tag == "img":
            self._flush()
            self.containers[-1].blocks.append(Image(alt=a.get("alt") or "", ref=a.get("src")))

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in ("br", "img", "hr"):
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in _EMPHASIS:
            if len(self.style) > 1:
                self.style.pop()
        elif tag == "a":
            if len(self.links) > 1:
                self.links.pop()
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            self._flush()
            self.heading = None
        elif tag in _BLOCK:
            self._flush()
            if tag == "pre":
                self.pre = max(0, self.pre - 1)
        elif tag in ("ul", "ol"):
            self._flush()
            if self.lists:
                self.lists.pop()
        elif tag == "li":
            self._flush()
            if len(self.containers) > 1:
                self.containers.pop()
        elif tag in ("td", "th"):
            self._flush()
            if len(self.containers) > 1:
                self.containers.pop()
        elif tag == "table":
            self._flush()
            if self.tables:
                self.tables.pop()

    def close(self) -> None:
        super().close()
        self._flush()


def _int(value: Optional[str]) -> int:
    try:
        return max(1, int(value or 1))
    except ValueError:
        return 1


def _collapse(runs: list[Run]) -> list[Run]:
    """HTML whitespace: runs of spaces and newlines read as one space, and
    the ends of a block are trimmed. A ``<br>`` (a run that is exactly a
    newline) is kept."""
    out = []
    for r in runs:
        text = r.text if r.text == "\n" else " ".join(r.text.split()) + (" " if r.text[-1:].isspace() else "")
        if r.text[:1].isspace() and r.text != "\n":
            text = " " + text.lstrip()
        out.append(Run(text, r.bold, r.italic, r.underline, r.strike, r.link))
    if out:
        out[0] = Run(out[0].text.lstrip(" "), out[0].bold, out[0].italic, out[0].underline, out[0].strike,
                     out[0].link)
        out[-1] = Run(out[-1].text.rstrip(" "), out[-1].bold, out[-1].italic, out[-1].underline,
                      out[-1].strike, out[-1].link)
    return merge_runs(out)


def html_blocks(text: str) -> tuple[list[Block], Optional[str]]:
    """The blocks of an HTML document, and its first heading's text."""
    b = _Builder()
    b.feed(text)
    b.close()
    return b.root.blocks, b.title
