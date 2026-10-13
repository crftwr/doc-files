"""EPUB books (``.epub``): one section per chapter, in reading order.

``META-INF/container.xml`` names the package document; its spine gives the
order of the XHTML chapters, each read by :mod:`.html`. The book's title and
author come from the package metadata.
"""

from __future__ import annotations

import posixpath
from typing import Optional

from ..model import Document, Section
from .._zipxml import local, member_xml, open_zip, read_member
from .html import html_blocks

OPF = "{http://www.idpf.org/2007/opf}"
CONTAINER = "{urn:oasis:names:tc:opendocument:xmlns:container}"


def read(data: bytes, password: Optional[str] = None) -> Document:
    z = open_zip(data)
    doc = Document(format="epub")
    container = member_xml(z, "META-INF/container.xml")
    rootfile = container.find(f".//{CONTAINER}rootfile") if container is not None else None
    if rootfile is None:
        doc.warnings.append("no META-INF/container.xml: not an EPUB book")
        return doc
    opf_path = rootfile.get("full-path", "")
    opf = member_xml(z, opf_path)
    if opf is None:
        doc.warnings.append(f"missing package document {opf_path}")
        return doc
    base = posixpath.dirname(opf_path)
    metadata = opf.find(f"{OPF}metadata")
    if metadata is not None:
        for el in metadata:
            name, text = local(el.tag), (el.text or "").strip()
            if name == "title" and text and "title" not in doc.meta:
                doc.meta["title"] = text
            elif name == "creator" and text and "author" not in doc.meta:
                doc.meta["author"] = text
    manifest = {item.get("id"): item for item in opf.iter(f"{OPF}item")}
    if any(item.get("properties", "").find("encrypted") >= 0 for item in manifest.values()) or \
            read_member(z, "META-INF/encryption.xml") is not None:
        doc.warnings.append("this book uses encryption (DRM); protected chapters cannot be read")
    n = 0
    for ref in opf.iter(f"{OPF}itemref"):
        item = manifest.get(ref.get("idref"))
        if item is None:
            continue
        media = item.get("media-type", "")
        if "html" not in media:
            continue
        path = posixpath.normpath(posixpath.join(base, item.get("href", "")))
        raw = read_member(z, path)
        if raw is None:
            continue
        blocks, title = html_blocks(raw.decode("utf-8", errors="replace"))
        if not blocks:
            continue
        n += 1
        doc.sections.append(Section("chapter", blocks, title=title, number=n))
    return doc
