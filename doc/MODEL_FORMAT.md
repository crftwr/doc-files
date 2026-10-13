# The document model

`doc_files.read()` returns a `Document`, and `Document.to_dict()` (or
`doc-files dump -f json`) gives the same thing as plain JSON-able data. This
page specifies that data. It is a contract: programs that render or search
documents read it, so a change that breaks a reader bumps `version`.

The model carries what a document **means** — headings and their levels,
lists and their nesting, tables and their merged cells, which slide a note
belongs to — and none of its **geometry**: no positions, sizes, fonts or
columns. What comes out can be searched, selected, copied and wrapped to
any width.

## Document

```json
{
  "model": "doc-files",
  "version": 1,
  "format": "pptx",
  "meta": {"title": "Results", "author": "A. Writer"},
  "warnings": [],
  "sections": [ ... ]
}
```

| Key | Meaning |
|---|---|
| `model` | Always `"doc-files"`. |
| `version` | `1`. |
| `format` | The reader that produced it: `pdf`, `docx`, `xlsx`, `pptx`, `odt`, `ods`, `odp`, `epub`. |
| `meta` | What the file says about itself: `title`, `author`, `subject`, when present. |
| `warnings` | What could not be read, in words for a person: "this PDF has no text layer — probably a scanned document", "sheet 'Data' cut at 20000 rows × 500 columns". |
| `sections` | The parts of the document, in order. |

## Section

```json
{"kind": "slide", "number": 3, "title": "Results", "hidden": true,
 "blocks": [ ... ], "notes": [ ... ], "furniture": [ ... ]}
```

| Key | Meaning |
|---|---|
| `kind` | `body` (a word processor document has one), `page`, `slide`, `sheet` or `chapter`. |
| `number` | Counts from 1 within the document. |
| `title` | A slide's title, a sheet's name, a chapter's first heading. |
| `hidden` | A hidden slide or sheet. Omitted when false. |
| `blocks` | The body. |
| `notes` | A slide's speaker notes, as blocks. Omitted when empty. |
| `furniture` | What repeats around the body: page headers and footers, a slide's date, footer and number. A reader may show it apart or leave it out. Omitted when empty. |

`notes` and `furniture` are **layers**: text that belongs to the section but
is not its body.

## Blocks

Every block has a `type`.

| `type` | Keys |
|---|---|
| `heading` | `level` (1–6), `runs` |
| `paragraph` | `runs` |
| `list` | `ordered` (bool), `items`: a list of items, each a list of blocks. A nested list is a `list` block inside an item. |
| `table` | `rows`: a list of rows, each a list of cells. `header_rows`: how many rows at the top are headers (omitted when 0). |
| `image` | `alt`: the alternative text. `ref`: where the picture lives inside the file, when known. The pixels are not carried. |

A **cell** is `{"blocks": [...], "colspan": n, "rowspan": n}`, with the spans
omitted when 1. As in HTML, a cell covered by another cell's span is not
listed, so a row may hold fewer cells than the table has columns.

## Runs

Text is a list of runs, each a stretch with one set of attributes:

```json
{"text": "grew", "bold": true, "italic": true, "underline": true, "strike": true, "link": "https://…"}
```

Only `text` is always present. The other keys appear only when true (or
set). A run's `text` may contain `\n` (a line break within the paragraph)
and `\t`.

## What each format gives

| Format | Sections | Notes |
|---|---|---|
| `docx` | one `body` | Headings from styles with an outline level. Lists from numbering, including Word's "List Bullet 2"-style depth. Merged table cells. Headers and footers as `furniture`. |
| `xlsx` | one `sheet` each | A table of cell values: the cached result of a formula, the text of a string. Number formats are not applied, so a date is its serial number. Merged ranges as spans. |
| `pptx` | one `slide` each | Title placeholder as `title`. Body placeholders as (nested) lists. Shapes in reading order, top to bottom and then left to right. Tables with spans. Date, footer and slide number as `furniture`. Speaker notes as `notes`. |
| `odt` `ods` `odp` | `body`, `sheet` or `slide` | As their Office counterparts. |
| `epub` | one `chapter` each | Spine order. HTML structure. |
| `pdf` | one `page` each | The page's text in reading order, in paragraphs where pypdf leaves blank lines. A PDF stores glyphs at positions, not structure, so no headings, lists or tables are guessed. |

## Versioning

New optional keys may be added to version 1. Readers ignore keys they don't
know. A change that would make a version 1 reader show something wrong gets
a new `version`.
