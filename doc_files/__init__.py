"""doc-files — what a document says, as structure: headings, paragraphs,
lists, tables, and the pages, slides, sheets or chapters they sit in.

Reads PDF, Word, Excel and PowerPoint (``.docx`` ``.xlsx`` ``.pptx``),
OpenDocument (``.odt`` ``.ods`` ``.odp``) and EPUB into one document model
(:mod:`doc_files.model`), and renders it as plain text or Markdown
(:mod:`doc_files.render`). The model carries meaning, not geometry: what
comes out can be searched, selected, copied and wrapped, which a picture of
a page cannot.

::

    import doc_files

    doc = doc_files.read("report.docx")
    print(doc_files.to_markdown(doc))
"""

from __future__ import annotations

__version__ = "0.1.0"

from .errors import DocumentError, MissingDependency, PasswordRequired, UnsupportedFormat
from .model import (MODEL_VERSION, Cell, Document, Heading, Image, ListBlock, Paragraph, Run, Section, Table,
                    document_from_dict)
from .readers import formats, read, read_bytes, supports
from .render import section_label, to_markdown, to_text

__all__ = [
    "__version__", "read", "read_bytes", "formats", "supports", "to_text", "to_markdown", "section_label",
    "Document", "Section", "Heading", "Paragraph", "ListBlock", "Table", "Cell", "Image", "Run",
    "document_from_dict", "MODEL_VERSION",
    "DocumentError", "UnsupportedFormat", "PasswordRequired", "MissingDependency",
]
