"""Fixtures: documents written by the libraries that write each format, so
the readers are tested against real writers' output. Nothing is committed;
every file is made in a temporary directory."""

import zipfile

import pytest


@pytest.fixture
def docx_file(tmp_path):
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.sections[0].header.paragraphs[0].text = "Confidential"
    d.add_heading("Annual Report", 1)
    d.add_heading("Summary", 2)
    p = d.add_paragraph("Revenue ")
    p.add_run("grew").bold = True
    p.add_run(" in ")
    p.add_run("every").italic = True
    p.add_run(" region.")
    d.add_paragraph("North", style="List Bullet")
    d.add_paragraph("Coast", style="List Bullet 2")
    d.add_paragraph("South", style="List Bullet")
    d.add_paragraph("First step", style="List Number")
    d.add_paragraph("Second step", style="List Number")
    t = d.add_table(rows=3, cols=3)
    t.cell(0, 0).merge(t.cell(0, 1))
    t.cell(0, 0).text = "Region"
    t.cell(0, 2).text = "Total"
    t.cell(1, 0).merge(t.cell(2, 0))
    t.cell(1, 0).text = "North"
    for r in (1, 2):
        t.cell(r, 1).text = f"Q{r}"
        t.cell(r, 2).text = str(r * 10)
    path = tmp_path / "report.docx"
    d.save(path)
    return path


@pytest.fixture
def xlsx_file(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Budget"
    ws.append(["Item", "Cost", "Approved"])
    ws.append(["Laptop", 1200, True])
    ws.append(["Desk", 350.5, False])
    ws.merge_cells("A5:C5")
    ws["A5"] = "Total pending"
    hidden = wb.create_sheet("Notes")
    hidden["B2"] = "internal"
    hidden.sheet_state = "hidden"
    path = tmp_path / "budget.xlsx"
    wb.save(path)
    return path


@pytest.fixture
def pptx_file(tmp_path):
    pptx = pytest.importorskip("pptx")
    from pptx.util import Inches
    prs = pptx.Presentation()
    s1 = prs.slides.add_slide(prs.slide_layouts[1])
    s1.shapes.title.text = "Results"
    body = s1.placeholders[1].text_frame
    body.text = "Sales up"
    sub = body.add_paragraph()
    sub.text = "Mostly in the north"
    sub.level = 1
    body.add_paragraph().text = "Costs flat"
    s1.notes_slide.notes_text_frame.text = "Mention the new office."
    s2 = prs.slides.add_slide(prs.slide_layouts[5])
    s2.shapes.title.text = "Numbers"
    rows, cols = 3, 2
    table = s2.shapes.add_table(rows, cols, Inches(1), Inches(2), Inches(4), Inches(2)).table
    table.cell(0, 0).merge(table.cell(0, 1))
    table.cell(0, 0).text = "Quarter results"
    table.cell(1, 0).text = "Q1"
    table.cell(1, 1).text = "10"
    table.cell(2, 0).text = "Q2"
    table.cell(2, 1).text = "12"
    # A text box above the table reads first.
    box = s2.shapes.add_textbox(Inches(1), Inches(1.2), Inches(4), Inches(0.5))
    box.text_frame.text = "In millions"
    s3 = prs.slides.add_slide(prs.slide_layouts[5])
    s3.shapes.title.text = "Backup"
    s3._element.set("show", "0")
    path = tmp_path / "deck.pptx"
    prs.save(path)
    return path


@pytest.fixture
def odt_file(tmp_path):
    pytest.importorskip("odf")
    from odf.opendocument import OpenDocumentText
    from odf.style import Style, TextProperties
    from odf.table import Table, TableCell, TableColumn, TableRow
    from odf.text import H, List, ListItem, P, Span

    doc = OpenDocumentText()
    bold = Style(name="B", family="text")
    bold.addElement(TextProperties(fontweight="bold"))
    doc.automaticstyles.addElement(bold)
    doc.text.addElement(H(outlinelevel=1, text="Minutes"))
    p = P(text="Attendees were ")
    p.addElement(Span(stylename=bold, text="all present"))
    p.addText(".")
    doc.text.addElement(p)
    lst = List()
    for item in ("Budget", "Hiring"):
        li = ListItem()
        li.addElement(P(text=item))
        lst.addElement(li)
    doc.text.addElement(lst)
    t = Table(name="Votes")
    t.addElement(TableColumn(numbercolumnsrepeated=2))
    for a, b in (("Motion", "Result"), ("A", "Passed")):
        tr = TableRow()
        for v in (a, b):
            tc = TableCell()
            tc.addElement(P(text=v))
            tr.addElement(tc)
        t.addElement(tr)
    doc.text.addElement(t)
    path = tmp_path / "minutes.odt"
    doc.save(str(path))
    return path


@pytest.fixture
def ods_file(tmp_path):
    pytest.importorskip("odf")
    from odf.opendocument import OpenDocumentSpreadsheet
    from odf.table import Table, TableCell, TableRow
    from odf.text import P

    doc = OpenDocumentSpreadsheet()
    t = Table(name="Scores")
    for row in (("Name", "Score"), ("Ann", "91")):
        tr = TableRow()
        for v in row:
            tc = TableCell()
            tc.addElement(P(text=v))
            tr.addElement(tc)
        # The trailing empty cells a spreadsheet writes, repeated far out.
        tr.addElement(TableCell(numbercolumnsrepeated=16000))
        t.addElement(tr)
    t.addElement(TableRow(numberrowsrepeated=1000000))
    doc.spreadsheet.addElement(t)
    path = tmp_path / "scores.ods"
    doc.save(str(path))
    return path


def make_epub(path, chapters, title="A Small Book"):
    """An EPUB with ``chapters`` (XHTML bodies) in spine order."""
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        z.writestr("META-INF/container.xml",
                   '<?xml version="1.0"?><container version="1.0" '
                   'xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles>'
                   '<rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>'
                   '</rootfiles></container>')
        items = "".join(f'<item id="c{i}" href="text/c{i}.xhtml" media-type="application/xhtml+xml"/>'
                        for i in range(len(chapters)))
        spine = "".join(f'<itemref idref="c{i}"/>' for i in reversed(range(len(chapters))))
        z.writestr("OEBPS/content.opf",
                   '<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="3.0">'
                   '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
                   f'<dc:title>{title}</dc:title><dc:creator>A. Writer</dc:creator></metadata>'
                   f'<manifest>{items}</manifest><spine>{spine}</spine></package>')
        for i, body in enumerate(chapters):
            z.writestr(f"OEBPS/text/c{i}.xhtml",
                       '<?xml version="1.0" encoding="utf-8"?><html xmlns="http://www.w3.org/1999/xhtml">'
                       f'<head><title>c{i}</title><style>p {{ color: red }}</style></head><body>{body}</body></html>')
    return path


def make_pdf(path, pages):
    """A minimal PDF whose pages draw ``pages`` (lists of lines) in Helvetica."""
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", None]
    kids = []
    font_obj = 3
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    for lines in pages:
        content = b""
        y = 720
        for line in lines:
            if line:
                safe = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
                content += b"BT /F1 12 Tf 72 %d Td (%s) Tj ET\n" % (y, safe.encode("latin-1"))
            y -= 18
        objs.append(b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream")
        content_no = len(objs)
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R "
                    b"/Resources << /Font << /F1 %d 0 R >> >> >>" % (content_no, font_obj))
        kids.append(len(objs))
    objs[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (
        b" ".join(b"%d 0 R" % k for k in kids), len(kids))
    out = b"%PDF-1.4\n"
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(out)
    return path
