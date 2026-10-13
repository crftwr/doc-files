"""Which reader reads which file, and the entry points."""

from __future__ import annotations

import importlib
import os
from typing import Callable, Optional, Union

from .errors import UnsupportedFormat
from .model import Document

#: Suffix → (module under ``doc_files.formats``, description).
_READERS: dict[str, tuple[str, str]] = {
    ".pdf": ("pdf", "PDF document"),
    ".docx": ("docx", "Word document"),
    ".docm": ("docx", "Word document (macro-enabled)"),
    ".xlsx": ("xlsx", "Excel workbook"),
    ".xlsm": ("xlsx", "Excel workbook (macro-enabled)"),
    ".pptx": ("pptx", "PowerPoint presentation"),
    ".pptm": ("pptx", "PowerPoint presentation (macro-enabled)"),
    ".odt": ("odf", "OpenDocument text"),
    ".ods": ("odf", "OpenDocument spreadsheet"),
    ".odp": ("odf", "OpenDocument presentation"),
    ".epub": ("epub", "EPUB book"),
}


def formats() -> dict[str, str]:
    """Every suffix a reader handles, with what it is."""
    return {suffix: desc for suffix, (_m, desc) in _READERS.items()}


def supports(name: Union[str, os.PathLike]) -> bool:
    """Whether a file with this name (or suffix) has a reader."""
    return _suffix(name) in _READERS


def _suffix(name) -> str:
    text = os.fspath(name)
    if text.startswith(".") and "/" not in text and "\\" not in text and text.count(".") == 1:
        return text.lower()
    return os.path.splitext(text)[1].lower()


def _reader(suffix: str) -> Callable[..., Document]:
    entry = _READERS.get(suffix)
    if entry is None:
        raise UnsupportedFormat(f"no reader for {suffix or 'files without an extension'}")
    return importlib.import_module(f".formats.{entry[0]}", __package__).read


def read_bytes(data: bytes, suffix: str, *, password: Optional[str] = None) -> Document:
    """Read a document from its bytes; ``suffix`` (``".docx"``) picks the
    reader. Raises :class:`~doc_files.errors.DocumentError` (and its
    subclasses) when the file cannot be read."""
    return _reader(_suffix(suffix))(data, password)


def read(path: Union[str, os.PathLike], *, password: Optional[str] = None) -> Document:
    """Read the document at ``path``."""
    reader = _reader(_suffix(path))
    with open(path, "rb") as f:
        data = f.read()
    return reader(data, password)
