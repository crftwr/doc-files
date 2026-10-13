"""Reading the zip-of-XML formats (OOXML, ODF, EPUB) safely.

A document is untrusted input. Two things keep a hostile one from taking the
reader down: every member is read with a size cap (a zip bomb inflates a
small file into gigabytes), and XML with a DOCTYPE is refused (entity
expansion — "billion laughs" — needs one, and none of these formats uses
one).
"""

from __future__ import annotations

import io
import zipfile
import xml.etree.ElementTree as ET
from typing import Optional

from .errors import DocumentError

#: The most one member may inflate to.
MAX_MEMBER = 256 * 1024 * 1024


def open_zip(data: bytes) -> zipfile.ZipFile:
    try:
        return zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise DocumentError(f"not a valid file: {e}") from None


def read_member(z: zipfile.ZipFile, name: str) -> Optional[bytes]:
    """A member's bytes, or None when the zip has no such member."""
    try:
        info = z.getinfo(name)
    except KeyError:
        return None
    if info.file_size > MAX_MEMBER:
        raise DocumentError(f"{name} is too large ({info.file_size} bytes)")
    with z.open(info) as f:
        data = f.read(MAX_MEMBER + 1)
    if len(data) > MAX_MEMBER:
        raise DocumentError(f"{name} is too large")
    return data


def parse_xml(data: bytes) -> ET.Element:
    head = data[:4096]
    if b"<!DOCTYPE" in head or b"<!ENTITY" in data:
        raise DocumentError("XML with a DOCTYPE is not read")
    try:
        return ET.fromstring(data)
    except ET.ParseError as e:
        raise DocumentError(f"malformed XML: {e}") from None


def member_xml(z: zipfile.ZipFile, name: str) -> Optional[ET.Element]:
    data = read_member(z, name)
    return None if data is None else parse_xml(data)


def local(tag: str) -> str:
    """``{namespace}name`` → ``name``."""
    return tag.rsplit("}", 1)[-1]
