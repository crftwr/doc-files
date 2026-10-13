"""PDF (``.pdf``): one section per page, through pypdf (an optional
dependency: ``pip install 'doc-files[pdf]'``).

A PDF stores glyphs at positions, not paragraphs, so what can be recovered is
the text of each page in reading order, as pypdf's extraction gives it —
lines kept as lines, blank lines as paragraph breaks. Headings, lists and
tables are not reconstructed from geometry: that would be guessing, and the
model promises structure the file actually has.

Two cases are reported rather than shown as an empty document: a PDF with no
text layer (a scan — OCR is out of scope), and one that needs a password.
"""

from __future__ import annotations

import io
from typing import Optional

from ..errors import DocumentError, MissingDependency, PasswordRequired
from ..model import Document, Paragraph, Run, Section


def read(data: bytes, password: Optional[str] = None) -> Document:
    try:
        from pypdf import PdfReader
        from pypdf.errors import PdfReadError
    except ImportError:
        raise MissingDependency("reading PDF needs pypdf: pip install 'doc-files[pdf]'") from None
    try:
        reader = PdfReader(io.BytesIO(data))
    except PdfReadError as e:
        raise DocumentError(f"not a readable PDF: {e}") from None
    if reader.is_encrypted:
        try:
            ok = reader.decrypt(password or "")
        except Exception as e:  # noqa: BLE001 — pypdf raises several kinds here
            raise PasswordRequired(f"this PDF is encrypted and cannot be opened: {e}") from None
        if not ok:
            raise PasswordRequired("this PDF is password-protected")
    doc = Document(format="pdf")
    try:
        info = reader.metadata or {}
        if info.get("/Title"):
            doc.meta["title"] = str(info["/Title"]).strip()
        if info.get("/Author"):
            doc.meta["author"] = str(info["/Author"]).strip()
    except Exception:  # noqa: BLE001 — metadata is a nicety, never a failure
        pass
    found_text = False
    for n, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text() or ""
        except Exception as e:  # noqa: BLE001 — one bad page does not lose the rest
            doc.warnings.append(f"page {n} could not be read: {e}")
            text = ""
        section = Section("page", number=n)
        for para in _paragraphs(text):
            section.blocks.append(Paragraph([Run(para)]))
        if section.blocks:
            found_text = True
        doc.sections.append(section)
    if reader.pages and not found_text:
        doc.warnings.append("this PDF has no text layer — probably a scanned document")
    return doc


def _paragraphs(text: str) -> list[str]:
    """Split a page's text at blank lines; keep the lines inside."""
    paras, current = [], []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if line.strip():
            current.append(line.rstrip())
        elif current:
            paras.append("\n".join(current))
            current = []
    if current:
        paras.append("\n".join(current))
    return paras
