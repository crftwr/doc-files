"""The model's dict form, the two renderers, and the command line."""

import json

from doc_files import (Cell, Document, Heading, Image, ListBlock, Paragraph, Run, Section, Table,
                       document_from_dict, to_markdown, to_text)
from doc_files.cli import main

from conftest import make_epub


def _sample():
    return Document("docx", [
        Section("body", [
            Heading(1, [Run("Plan")]),
            Paragraph([Run("A "), Run("bold", bold=True), Run(" #1 * claim", italic=True),
                       Run("site", link="https://example.com")]),
            ListBlock(True, [[Paragraph([Run("one")]), ListBlock(False, [[Paragraph([Run("inner")])]])],
                             [Paragraph([Run("two")])]]),
            Table([[Cell([Paragraph([Run("wide")])], colspan=2)],
                   [Cell([Paragraph([Run("a|b")])]), Cell([Paragraph([Run("c")])])]], header_rows=1),
            Image("A chart", "media/1.png"),
        ], furniture=[Paragraph([Run("Page footer")])]),
    ], meta={"title": "Plan"}, warnings=["something was skipped"])


def test_dict_round_trip():
    doc = _sample()
    data = json.loads(json.dumps(doc.to_dict()))
    assert data["model"] == "doc-files" and data["version"] == 1
    again = document_from_dict(data)
    assert again.to_dict() == doc.to_dict()


def test_markdown_keeps_structure_and_escapes_text():
    md = to_markdown(_sample())
    assert md.startswith("# Plan\n") and md.count("# Plan") == 1   # title = first heading
    assert "**bold**" in md and "*#1 \\* claim*" in md
    assert "[site](https://example.com)" in md
    assert "1. one\n   - inner\n2. two" in md
    assert "| wide |  |" in md and "a\\|b" in md
    assert "*[image: A chart]*" in md
    assert "> something was skipped" in md
    assert "Page footer" not in md   # furniture is not body


def test_text_is_the_words_in_order():
    text = to_text(_sample())
    assert "A bold #1 * claimsite" in text
    assert "1. one\n   - inner\n2. two" in text
    assert "wide\t" in text and "a|b\tc" in text


def test_sections_get_labels():
    doc = Document("pptx", [Section("slide", [Paragraph([Run("x")])], title="Intro", number=1),
                            Section("slide", [], number=2, hidden=True,
                                    notes=[Paragraph([Run("say hi")])])])
    md = to_markdown(doc)
    assert "## Slide 1: Intro" in md and "## Slide 2 (hidden)" in md
    assert "**Notes**\n\nsay hi" in md
    assert "== Slide 1: Intro ==" in to_text(doc)


def test_cli_dump_and_formats(tmp_path, capsys):
    path = make_epub(tmp_path / "b.epub", ["<h1>Only</h1><p>Text.</p>"])
    assert main(["dump", str(path), "-f", "json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["format"] == "epub" and data["sections"][0]["title"] == "Only"
    assert main(["dump", str(path), "-f", "markdown"]) == 0
    assert "## Chapter 1: Only" in capsys.readouterr().out
    assert main(["formats"]) == 0
    assert ".pptx" in capsys.readouterr().out
    assert main(["dump", str(tmp_path / "x.doc")]) == 1
