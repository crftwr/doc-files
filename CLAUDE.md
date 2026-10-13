# doc-files — Claude Code Instructions

doc-files reads what a document says — PDF, Word, Excel, PowerPoint,
OpenDocument, EPUB — into one **document model**, and renders it as plain
text or Markdown. It is a **library first and a CLI second**.

Its first user is **[XeFM](https://github.com/crftwr/xefm)**, a dual-pane
file manager, whose document text viewer and content search read files
through it (xefm discussion #548, issue #575). A PuiKit widget that renders
the model directly, with more than Markdown can express (merged cells,
layers), is planned; the model is the contract between the two.

The package is `doc_files/` at the repo root (flat layout, as XeFM, PuiKit
and similar-files have it). Tests live in `test/`, docs in `doc/`.

---

## The boundary: meaning, not geometry

The model carries what a document **means** — heading levels, list nesting,
merged table cells, which slide a note belongs to — and **no geometry**: no
positions, sizes, fonts or columns. Everything that comes out must survive
being searched, selected, copied and re-wrapped. Before adding anything to
the model, ask whether it is meaning or appearance.

- **Slides** are the hard case: their meaning is partly where things sit.
  Position is used only for **reading order** (top to bottom, then left to
  right); no coordinate reaches the model.
- **PDF** stores glyphs at positions. Read the text a page has, in reading
  order; never reconstruct headings, lists or tables from geometry. That
  would be guessing, and the model promises structure the file actually has.
- **Layers**, after Docling's model: text that belongs to a section but is
  not its body goes to `notes` (speaker notes) or `furniture` (headers,
  footers, slide numbers), never into `blocks`.

Out of scope, on purpose: the old binary Office formats (`.doc`, `.xls`,
`.ppt`), OCR, page rendering.

## Why not Docling, pandoc or MarkItDown

Checked before writing this (October 2026):

- **Docling** has the closest model (layers, spans, chapters) but is about
  230 MB with numpy and pandas even in its slim office-only build, needs ML
  models for PDF, and does not read EPUB.
- **pandoc** has a rich AST but reads no PDF and is an external binary to
  ship.
- **MarkItDown** produces Markdown only, which is the limit this library
  exists to get past.

XeFM ships in a DMG and an MSIX, so size and dependencies matter. The core
is **standard library only**. PDF uses **pypdf** (pure Python), an optional
extra.

---

## Terminal session rules

### Virtual environment

- The venv lives at `.venv/` (`make dev`). Assume it is active in ongoing
  sessions; activate it only when starting fresh, as a separate command:
  ```bash
  source .venv/bin/activate
  python -m pytest
  ```

### Running things

Run everything **from the repo root**:

```bash
python -m pytest test/ -v
python -m doc_files dump some.docx -f markdown
```

### Git

- Use `--no-pager` for any git command that may page output.
- Commit and push only when the user asks.
- **Before version 1.0**, commit directly to `main`; no branch or PR.
  **From 1.0 on**, work on a branch and open a PR. The version is
  `__version__` in `doc_files/__init__.py`.

### Real documents

Don't open the user's own documents unless asked. Test on generated files.
Source code, docs and tests published to GitHub name only **made-up**
documents and content (`report.docx`, "Quarterly Report"), never a real file
name or text seen on the user's machine.

---

## Coding standards

- **Logging:** `logger = logging.getLogger(__name__)` in library modules,
  never configured there. `print()` only in `doc_files/cli.py`.
- **Errors:** a reader raises `DocumentError` (or a subclass:
  `UnsupportedFormat`, `PasswordRequired`, `MissingDependency`) when the file
  cannot be read at all. A part that cannot be read (one page, one sheet)
  goes into `Document.warnings`, and the rest is still returned.
- **Untrusted input:** zip members through `_zipxml.read_member` (size cap),
  XML through `_zipxml.parse_xml` (no DOCTYPE). Expand repeats (ODF's
  `number-*-repeated`) only as far as they hold something, and cap sheets.
- **Text:** read and write UTF-8 explicitly.
- Type hints on public functions. Docstrings say what a function is for and
  what a caller can rely on. Python files are not executable.

---

## Tests

- `test/test_*.py`, run with `pytest`.
- **Generate fixtures with the formats' own writers** (python-docx,
  python-pptx, openpyxl, odfpy, pypdf, in the `test` extra), so readers are
  tested against real writers' output. EPUB and minimal PDFs are built in
  `conftest.py`. Never commit a document.
- A test that needs an extra skips cleanly without it (`pytest.importorskip`);
  `make test-core` runs the suite on a bare install.

## File placement

| What | Where |
|---|---|
| Package | `doc_files/`; one reader per format in `doc_files/formats/` |
| CLI | `doc_files/cli.py`, `doc_files/__main__.py` |
| Tests | `test/test_*.py` |
| User docs, the model contract | `doc/` |
| Throwaway files | `temp/` (git-ignored) |

`doc/MODEL_FORMAT.md` is a contract other programs depend on. Change it in
the same commit as the model.
