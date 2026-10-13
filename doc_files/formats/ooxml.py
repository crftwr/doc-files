"""Pieces the three Office Open XML readers share: relationships and the
document properties."""

from __future__ import annotations

import posixpath

from .._zipxml import local, member_xml

PKG_R = "{http://schemas.openxmlformats.org/package/2006/relationships}"


def relationships(z, part: str) -> dict[str, dict]:
    """``{rId: {"target", "type", "external"}}`` for ``part``. Internal
    targets are left as written (relative to ``part``'s folder)."""
    folder, name = posixpath.split(part)
    root = member_xml(z, posixpath.join(folder, "_rels", name + ".rels"))
    out: dict[str, dict] = {}
    if root is None:
        return out
    for rel in root.iter(f"{PKG_R}Relationship"):
        out[rel.get("Id", "")] = {
            "target": rel.get("Target", ""),
            "type": rel.get("Type", ""),
            "external": rel.get("TargetMode") == "External",
        }
    return out


def resolve(part: str, target: str) -> str:
    """An internal relationship target as a member name."""
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(part), target))


def core_meta(z) -> dict[str, str]:
    """``title`` and ``author`` from ``docProps/core.xml``, when present."""
    root = member_xml(z, "docProps/core.xml")
    meta: dict[str, str] = {}
    if root is None:
        return meta
    for el in root:
        name = local(el.tag)
        text = (el.text or "").strip()
        if not text:
            continue
        if name == "title":
            meta["title"] = text
        elif name == "creator":
            meta["author"] = text
        elif name == "subject":
            meta["subject"] = text
    return meta
