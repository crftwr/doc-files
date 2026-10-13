"""The command line: ``doc-files dump FILE`` and ``doc-files formats``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from typing import Optional, Sequence

from . import __version__, formats, read, to_markdown, to_text
from .errors import DocumentError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="doc-files", description="Read what a document says, as text, Markdown or a JSON model.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    dump = sub.add_parser("dump", help="print a document as text, Markdown or JSON")
    dump.add_argument("file")
    dump.add_argument("-f", "--format", choices=["text", "markdown", "json"], default="text")
    dump.add_argument("--password", help="for an encrypted PDF")
    sub.add_parser("formats", help="list the file types that can be read")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    if args.command == "formats":
        for suffix, desc in formats().items():
            print(f"{suffix:<7} {desc}")
        return 0
    try:
        doc = read(args.file, password=args.password)
    except (DocumentError, OSError) as e:
        print(f"doc-files: {args.file}: {e}", file=sys.stderr)
        return 1
    if args.format == "json":
        out = json.dumps(doc.to_dict(), ensure_ascii=False, indent=1)
    elif args.format == "markdown":
        out = to_markdown(doc)
    else:
        out = to_text(doc)
    sys.stdout.write(out if out.endswith("\n") else out + "\n")
    for w in doc.warnings:
        print(f"doc-files: {w}", file=sys.stderr)
    return 0
