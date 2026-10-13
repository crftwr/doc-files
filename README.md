# doc-files

Read what PDF, Office, OpenDocument and EPUB files **say**: their text and
its structure, from headings and lists to tables and the pages, slides,
sheets or chapters they sit in. You get a document model, plain text or
Markdown.

> **Status: early development.** The model and the command line may still
> change between releases.

## What it reads

| Files | Needs |
|---|---|
| Word `.docx`, Excel `.xlsx`, PowerPoint `.pptx` | nothing beyond Python |
| OpenDocument `.odt` `.ods` `.odp` | nothing beyond Python |
| EPUB `.epub` | nothing beyond Python |
| PDF `.pdf` | [pypdf](https://pypi.org/project/pypdf/) (`pip install "doc-files[pdf]"`) |

The old binary Office formats (`.doc`, `.xls`, `.ppt`) are not read.

## How it works

```bash
pip install "doc-files[pdf]"

doc-files dump report.docx                # plain text
doc-files dump deck.pptx -f markdown      # Markdown: a section per slide, notes included
doc-files dump budget.xlsx -f json        # the document model
doc-files formats                         # what can be read
```

```python
import doc_files

doc = doc_files.read("deck.pptx")
for section in doc.sections:            # one per slide
    print(section.number, section.title, len(section.notes))
print(doc_files.to_markdown(doc))
```

## What you get, and what you don't

The model keeps what a document **means**:

- headings and their levels;
- lists and their nesting;
- tables with their merged cells;
- emphasis and links;
- a slide's speaker notes, page headers and footers, each in its own layer.

It leaves out how the document **looks**: positions, fonts, sizes, page
layout. That is the point. The result can be searched, selected, copied and
wrapped to any width, which a picture of a page cannot. To see what a file
looks like, open it in the application that made it.

A PDF stores glyphs at positions rather than paragraphs and tables, so from a
PDF you get the text of each page in reading order, and nothing guessed from
the layout. A scanned PDF has no text at all; doc-files says so instead of
returning an empty document. It does no OCR.

The model is specified in
[doc/MODEL_FORMAT.md](https://github.com/crftwr/doc-files/blob/main/doc/MODEL_FORMAT.md).
[XeFM](https://github.com/crftwr/xefm), a dual-pane file manager, uses it to
show documents as text.

## Safety

Documents are untrusted input. Zip members are read with a size cap (no zip
bombs), and XML with a DOCTYPE is refused (no entity expansion). doc-files
only reads files. It never writes or changes them.

## License

MIT
