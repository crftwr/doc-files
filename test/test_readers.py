"""Each reader against a file its format's own writer made."""

import io

import pytest

import doc_files
from doc_files import Heading, ListBlock, Paragraph, Table, to_text
from doc_files.model import runs_text

from conftest import make_epub, make_pdf


def _texts(blocks):
    out = []
    for b in blocks:
        if isinstance(b, (Heading, Paragraph)):
            out.append(runs_text(b.runs))
        elif isinstance(b, ListBlock):
            for item in b.items:
                out.extend(_texts(item))
        elif isinstance(b, Table):
            for row in b.rows:
                for c in row:
                    out.extend(_texts(c.blocks))
    return out


# --- docx ---------------------------------------------------------------------

def test_docx_headings_emphasis_and_furniture(docx_file):
    doc = doc_files.read(docx_file)
    (body,) = doc.sections
    assert body.kind == "body"
    h1, h2, para = body.blocks[:3]
    assert (h1.level, runs_text(h1.runs)) == (1, "Annual Report")
    assert (h2.level, runs_text(h2.runs)) == (2, "Summary")
    assert [(r.text, r.bold, r.italic) for r in para.runs] == [
        ("Revenue ", False, False), ("grew", True, False), (" in ", False, False),
        ("every", False, True), (" region.", False, False)]
    assert _texts(body.furniture) == ["Confidential"]
    assert "Confidential" not in _texts(body.blocks)


def test_docx_lists_nest_and_know_their_kind(docx_file):
    blocks = doc_files.read(docx_file).sections[0].blocks
    bullets, numbered = [b for b in blocks if isinstance(b, ListBlock)]
    assert not bullets.ordered and numbered.ordered
    assert [runs_text(item[0].runs) for item in bullets.items] == ["North", "South"]
    nested = bullets.items[0][1]
    assert isinstance(nested, ListBlock) and runs_text(nested.items[0][0].runs) == "Coast"
    assert [runs_text(item[0].runs) for item in numbered.items] == ["First step", "Second step"]


def test_docx_table_keeps_merged_cells(docx_file):
    table = next(b for b in doc_files.read(docx_file).sections[0].blocks if isinstance(b, Table))
    first, second, third = table.rows
    assert [(_texts(c.blocks), c.colspan, c.rowspan) for c in first] == [
        (["Region"], 2, 1), (["Total"], 1, 1)]
    assert (_texts(second[0].blocks), second[0].rowspan) == (["North"], 2)
    # The cell under the vertical merge is covered, so its row is one short.
    assert [_texts(c.blocks) for c in third] == [["Q2"], ["20"]]


# --- xlsx ---------------------------------------------------------------------

def test_xlsx_sheets_values_merges_and_hidden(xlsx_file):
    doc = doc_files.read(xlsx_file)
    budget, notes = doc.sections
    assert (budget.kind, budget.title, budget.number, budget.hidden) == ("sheet", "Budget", 1, False)
    assert notes.hidden
    (table,) = budget.blocks
    assert [_texts(c.blocks) for c in table.rows[0]] == [["Item"], ["Cost"], ["Approved"]]
    assert [_texts(c.blocks) for c in table.rows[1]] == [["Laptop"], ["1200"], ["TRUE"]]
    assert _texts(table.rows[2][1].blocks) == ["350.5"]
    merged = table.rows[4]
    assert (len(merged), merged[0].colspan, _texts(merged[0].blocks)) == (1, 3, ["Total pending"])


# --- pptx ---------------------------------------------------------------------

def test_pptx_titles_nested_bullets_and_notes(pptx_file):
    doc = doc_files.read(pptx_file)
    s1, s2, s3 = doc.sections
    assert (s1.kind, s1.number, s1.title) == ("slide", 1, "Results")
    (bullets,) = s1.blocks
    assert [runs_text(i[0].runs) for i in bullets.items] == ["Sales up", "Costs flat"]
    assert runs_text(bullets.items[0][1].items[0][0].runs) == "Mostly in the north"
    assert _texts(s1.notes) == ["Mention the new office."]
    assert s3.hidden and not s1.hidden


def test_pptx_reading_order_and_table_spans(pptx_file):
    s2 = doc_files.read(pptx_file).sections[1]
    assert s2.title == "Numbers"
    assert isinstance(s2.blocks[0], Paragraph) and runs_text(s2.blocks[0].runs) == "In millions"
    table = s2.blocks[1]
    assert (table.rows[0][0].colspan, _texts(table.rows[0][0].blocks)) == (2, ["Quarter results"])
    assert len(table.rows[0]) == 1


# --- OpenDocument -------------------------------------------------------------

def test_odt(odt_file):
    doc = doc_files.read(odt_file)
    assert doc.format == "odt"
    blocks = doc.sections[0].blocks
    assert isinstance(blocks[0], Heading) and runs_text(blocks[0].runs) == "Minutes"
    assert [(r.text, r.bold) for r in blocks[1].runs] == [
        ("Attendees were ", False), ("all present", True), (".", False)]
    assert isinstance(blocks[2], ListBlock) and len(blocks[2].items) == 2
    assert [_texts(c.blocks) for c in blocks[3].rows[1]] == [["A"], ["Passed"]]


def test_ods_does_not_expand_empty_repeats(ods_file):
    doc = doc_files.read(ods_file)
    assert doc.format == "ods"
    (sheet,) = doc.sections
    (table,) = sheet.blocks
    assert len(table.rows) == 2
    assert [[_texts(c.blocks) for c in row] for row in table.rows] == [
        [["Name"], ["Score"]], [["Ann"], ["91"]]]


# --- EPUB ---------------------------------------------------------------------

def test_epub_spine_order_and_html_structure(tmp_path):
    path = make_epub(tmp_path / "book.epub", [
        "<h1>Second</h1><p>After the first.</p>",
        "<h1>First</h1><p>Some <b>bold</b> and <a href='https://example.com'>a link</a>.</p>"
        "<ol><li>one<ul><li>inner</li></ul></li><li>two</li></ol>"
        "<table><tr><th colspan='2'>Head</th></tr><tr><td>a</td><td>b</td></tr></table>"
        "<p><img src='x.png' alt='A diagram'/></p><script>ignored()</script>",
    ])
    doc = doc_files.read(path)
    assert doc.meta == {"title": "A Small Book", "author": "A. Writer"}
    first, second = doc.sections
    assert (first.title, second.title) == ("First", "Second")   # spine order, not file order
    para = first.blocks[1]
    assert [(r.text, r.bold, r.link) for r in para.runs] == [
        ("Some ", False, None), ("bold", True, None), (" and ", False, None),
        ("a link", False, "https://example.com"), (".", False, None)]
    lst = first.blocks[2]
    assert lst.ordered and runs_text(lst.items[0][1].items[0][0].runs) == "inner"
    table = first.blocks[3]
    assert table.header_rows == 1 and table.rows[0][0].colspan == 2
    assert first.blocks[4].alt == "A diagram"
    assert "ignored" not in to_text(doc)


# --- PDF ----------------------------------------------------------------------

def test_pdf_pages_and_paragraphs(tmp_path):
    pytest.importorskip("pypdf")
    path = make_pdf(tmp_path / "r.pdf", [["Quarterly Report", "", "Revenue grew."], ["Page two"]])
    doc = doc_files.read(path)
    p1, p2 = doc.sections
    assert (p1.kind, p1.number, p2.number) == ("page", 1, 2)
    # pypdf gives a page's lines in reading order; a PDF has no paragraphs to
    # find, so the gap between these two lines is not one.
    assert "\n".join(_texts(p1.blocks)).split("\n") == ["Quarterly Report", "Revenue grew."]
    assert _texts(p2.blocks) == ["Page two"]
    assert not doc.warnings


def test_pdf_without_text_says_so(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    w = pypdf.PdfWriter()
    w.add_blank_page(612, 792)
    buf = io.BytesIO()
    w.write(buf)
    doc = doc_files.read_bytes(buf.getvalue(), ".pdf")
    assert doc.is_empty
    assert any("no text layer" in w for w in doc.warnings)


def test_pdf_with_a_password(tmp_path):
    pypdf = pytest.importorskip("pypdf")
    src = make_pdf(tmp_path / "s.pdf", [["Secret plans"]])
    w = pypdf.PdfWriter(clone_from=str(src))
    w.encrypt("pw", algorithm="RC4-128")
    buf = io.BytesIO()
    w.write(buf)
    with pytest.raises(doc_files.PasswordRequired):
        doc_files.read_bytes(buf.getvalue(), ".pdf")
    doc = doc_files.read_bytes(buf.getvalue(), ".pdf", password="pw")
    assert _texts(doc.sections[0].blocks) == ["Secret plans"]


# --- what is refused ----------------------------------------------------------

def test_refusals(tmp_path):
    with pytest.raises(doc_files.UnsupportedFormat):
        doc_files.read_bytes(b"", ".doc")
    with pytest.raises(doc_files.DocumentError):
        doc_files.read_bytes(b"not a zip", ".docx")


def test_xml_with_a_doctype_is_refused(tmp_path):
    import zipfile
    path = tmp_path / "bomb.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml",
                   '<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">]><w:document '
                   'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"/>')
    with pytest.raises(doc_files.DocumentError):
        doc_files.read(path)
