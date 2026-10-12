"""Renderers for PPTX / DOCX / XLSX / PDF / TXT and the verification that reopens every file.

A file is reported as ready only after it was read back with the same library family and its
structure matched the content (slide count, headings, rows, PDF text)."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from .model import DocumentContent, Section

# Colours of the A.R.C. presentation theme (amber on graphite).
BG = (0x16, 0x13, 0x10)
ACCENT = (0xFF, 0xB0, 0x00)
TEXT = (0xF2, 0xE6, 0xD0)
MUTED = (0xB8, 0xA8, 0x8C)
BULLETS_PER_SLIDE = 6
CHARS_PER_SLIDE = 700


class RenderError(RuntimeError):
    pass


@dataclass
class Verification:
    ok: bool
    details: list[str] = field(default_factory=list)
    pages: int = 0  # slides / pages / rows, depending on the format


def _squash(text: str) -> str:
    return re.sub(r"\W+", "", text.lower().replace("ё", "е"))


def slide_chunks(section: Section) -> list[list[str]]:
    """Bullets of one section split into slides (paragraphs become bullets in a presentation)."""
    items = section.bullets or section.paragraphs or [""]
    chunks: list[list[str]] = [[]]
    for item in items:
        size = sum(len(x) for x in chunks[-1])
        if chunks[-1] and (len(chunks[-1]) >= BULLETS_PER_SLIDE or size + len(item) > CHARS_PER_SLIDE):
            chunks.append([])
        chunks[-1].append(item)
    return chunks


def bullet_size(items: list[str]) -> int:
    total = sum(len(x) for x in items)
    return 26 if total <= 300 else 22 if total <= 480 else 18 if total <= 700 else 16


def expected_slides(content: DocumentContent) -> int:
    count = 1 + sum(len(slide_chunks(s)) for s in content.sections)
    count += 1 if content.table and content.table.rows else 0
    count += 1 if content.sources else 0
    return count


# ====================================================================== PPTX
def render_pptx(content: DocumentContent, path: str) -> None:
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]

    def background(slide) -> None:
        fill = slide.background.fill
        fill.solid()
        fill.fore_color.rgb = RGBColor(*BG)

    def textbox(slide, left, top, width, height, text, size, color, bold=False):
        box = slide.shapes.add_textbox(left, top, width, height)
        frame = box.text_frame
        frame.word_wrap = True
        para = frame.paragraphs[0]
        run = para.add_run()
        run.text = text
        run.font.size, run.font.bold, run.font.name = Pt(size), bold, "Segoe UI"
        run.font.color.rgb = RGBColor(*color)
        return frame

    def bar(slide):
        shape = slide.shapes.add_shape(1, Inches(0.6), Inches(1.35), Inches(1.2), Inches(0.06))
        shape.fill.solid()
        shape.fill.fore_color.rgb = RGBColor(*ACCENT)
        shape.line.fill.background()

    def content_slide(title: str):
        slide = prs.slides.add_slide(blank)
        background(slide)
        textbox(slide, Inches(0.6), Inches(0.4), Inches(12.1), Inches(0.9), title, 36, ACCENT, bold=True)
        bar(slide)
        return slide

    slide = prs.slides.add_slide(blank)
    background(slide)
    textbox(slide, Inches(0.8), Inches(2.4), Inches(11.7), Inches(1.6), content.title, 44, ACCENT, bold=True)
    if content.subtitle:
        textbox(slide, Inches(0.8), Inches(4.1), Inches(11.7), Inches(1.0), content.subtitle, 22, TEXT)
    textbox(slide, Inches(0.8), Inches(6.6), Inches(11.7), Inches(0.5), "Подготовлено A.R.C.", 12, MUTED)

    for section in content.sections:
        chunks = slide_chunks(section)
        for index, items in enumerate(chunks):
            title = section.heading if index == 0 else f"{section.heading} (продолжение)"
            slide = content_slide(title)
            frame = None
            size = bullet_size(items)
            for item in items:
                if not item:
                    continue
                if frame is None:
                    frame = textbox(slide, Inches(0.8), Inches(1.7), Inches(11.7), Inches(5.3), "• " + item, size, TEXT)
                else:
                    para = frame.add_paragraph()
                    run = para.add_run()
                    run.text = "• " + item
                    run.font.size, run.font.name = Pt(size), "Segoe UI"
                    run.font.color.rgb = RGBColor(*TEXT)
                    para.space_before = Pt(14)
            if section.paragraphs and section.bullets and index == 0:
                slide.notes_slide.notes_text_frame.text = "\n".join(section.paragraphs)

    if content.table and content.table.rows:
        slide = content_slide(content.title + ": таблица")
        rows = content.table.normalized_rows()[:14]
        cols = len(content.table.columns)
        shape = slide.shapes.add_table(len(rows) + 1, cols, Inches(0.6), Inches(1.7), Inches(12.1),
                                       Inches(0.4) * (len(rows) + 1))
        table = shape.table
        for c, name in enumerate(content.table.columns):
            table.cell(0, c).text = name
        for r, row in enumerate(rows, 1):
            for c, value in enumerate(row):
                table.cell(r, c).text = value
        for r in range(len(rows) + 1):
            for c in range(cols):
                cell = table.cell(r, c)
                cell.fill.solid()
                cell.fill.fore_color.rgb = RGBColor(*(ACCENT if r == 0 else (0x24, 0x1F, 0x19)))
                for para in cell.text_frame.paragraphs:
                    for run in para.runs:
                        run.font.size, run.font.bold = Pt(16), r == 0
                        run.font.color.rgb = RGBColor(*(BG if r == 0 else TEXT))

    if content.sources:
        slide = content_slide("Источники")
        text = "\n".join(f"{i}. {s.title} — {s.url}" for i, s in enumerate(content.sources, 1))
        textbox(slide, Inches(0.8), Inches(1.7), Inches(11.7), Inches(5.3), text, 16, TEXT)
    prs.save(path)


def verify_pptx(content: DocumentContent, path: str) -> Verification:
    from pptx import Presentation

    prs = Presentation(path)
    slides = list(prs.slides)
    details = []
    expected = expected_slides(content)
    if len(slides) != expected:
        details.append(f"слайдов {len(slides)}, ожидалось {expected}")
    texts = [shape.text_frame.text for shape in slides[0].shapes if shape.has_text_frame] if slides else []
    if content.title not in texts:
        details.append("на титульном слайде нет заголовка")
    return Verification(not details, details, len(slides))


# ====================================================================== DOCX
def render_docx(content: DocumentContent, path: str) -> None:
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name, style.font.size = "Calibri", Pt(11)
    doc.core_properties.title = content.title
    doc.core_properties.author = "A.R.C."
    doc.add_heading(content.title, level=0)
    if content.subtitle:
        doc.add_paragraph().add_run(content.subtitle).italic = True
    if content.note:
        doc.add_paragraph(content.note)
    for section in content.sections:
        doc.add_heading(section.heading, level=1)
        for paragraph in section.paragraphs:
            doc.add_paragraph(paragraph)
        for bullet in section.bullets:
            doc.add_paragraph(bullet, style="List Bullet")
    if content.table and content.table.rows:
        doc.add_heading("Таблица", level=1)
        rows = content.table.normalized_rows()
        table = doc.add_table(rows=len(rows) + 1, cols=len(content.table.columns))
        table.style = "Table Grid"
        for c, name in enumerate(content.table.columns):
            cell = table.cell(0, c)
            cell.text = name
            for run in cell.paragraphs[0].runs:
                run.bold = True
        for r, row in enumerate(rows, 1):
            for c, value in enumerate(row):
                table.cell(r, c).text = value
    if content.sources:
        doc.add_heading("Источники", level=1)
        for source in content.sources:
            doc.add_paragraph(f"{source.title} — {source.url}", style="List Number")
    doc.save(path)


def verify_docx(content: DocumentContent, path: str) -> Verification:
    from docx import Document

    doc = Document(path)
    texts = {p.text for p in doc.paragraphs}
    details = []
    if content.title not in texts:
        details.append("нет заголовка документа")
    missing = [s.heading for s in content.sections if s.heading not in texts]
    if missing:
        details.append("нет разделов: " + ", ".join(missing[:3]))
    if content.table and content.table.rows and not doc.tables:
        details.append("нет таблицы")
    return Verification(not details, details, len(doc.paragraphs))


# ====================================================================== XLSX
def table_for_sheet(content: DocumentContent) -> tuple[list[str], list[list[str]]]:
    if content.table and content.table.rows:
        return content.table.columns, content.table.normalized_rows()
    rows = []
    for section in content.sections:
        items = section.bullets + section.paragraphs or [""]
        for item in items:
            rows.append([section.heading, item])
    return ["Раздел", "Содержание"], rows


def render_xlsx(content: DocumentContent, path: str) -> None:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    columns, rows = table_for_sheet(content)
    wb = Workbook()
    ws = wb.active
    ws.title = "Данные"
    ws.append(columns)
    for row in rows:
        ws.append([_cell_value(v) for v in row])
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            if cell.data_type == "f":  # generated text must never become a formula
                cell.data_type = "s"
    header_fill = PatternFill("solid", fgColor="FFB000")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="16130F")
        cell.fill = header_fill
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    for index, name in enumerate(columns, 1):
        width = max([len(str(name))] + [len(str(r[index - 1])) for r in rows[:200]] + [8])
        ws.column_dimensions[get_column_letter(index)].width = min(60, width + 2)
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    if rows:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{len(rows) + 1}"
    info = wb.create_sheet("Описание")
    info.append([content.title])
    info["A1"].font = Font(bold=True, size=14)
    if content.subtitle:
        info.append([content.subtitle])
    if content.note:
        info.append([content.note])
    for source in content.sources:
        info.append([source.title, source.url])
    info.column_dimensions["A"].width = 60
    info.column_dimensions["B"].width = 60
    wb.properties.title = content.title
    wb.properties.creator = "A.R.C."
    wb.save(path)


def _cell_value(value: str):
    """Numbers stay numbers, so sorting and sums work in Excel."""
    text = value.strip()
    if re.fullmatch(r"-?\d{1,15}", text):
        return int(text)
    if re.fullmatch(r"-?\d{1,15}[.,]\d{1,6}", text):
        return float(text.replace(",", "."))
    return value


def verify_xlsx(content: DocumentContent, path: str) -> Verification:
    from openpyxl import load_workbook

    columns, rows = table_for_sheet(content)
    wb = load_workbook(path)
    details = []
    try:
        if "Данные" not in wb.sheetnames:
            return Verification(False, ["нет листа «Данные»"])
        sheet = wb["Данные"]
        values = list(sheet.iter_rows(values_only=True))
        if not values or [str(v) for v in values[0][:len(columns)]] != columns:
            details.append("заголовки столбцов не совпадают")
        if len(values) - 1 != len(rows):
            details.append(f"строк {len(values) - 1}, ожидалось {len(rows)}")
        if any(cell.data_type == "f" for row in sheet.iter_rows() for cell in row):
            details.append("в ячейках оказались формулы")
    finally:
        wb.close()
    return Verification(not details, details, len(rows))


# ====================================================================== PDF
FONT_CANDIDATES = [
    ("arial.ttf", "arialbd.ttf"), ("segoeui.ttf", "segoeuib.ttf"), ("calibri.ttf", "calibrib.ttf"),
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"), ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"),
]
FONT_DIRS = [os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
             "/usr/share/fonts/truetype/dejavu", "/usr/share/fonts/truetype/liberation",
             "/usr/share/fonts/TTF", "/Library/Fonts"]


def find_fonts(dirs: Optional[list[str]] = None) -> Optional[tuple[str, str]]:
    """A TrueType font with Cyrillic glyphs (regular, bold). Bold falls back to regular."""
    for regular, bold in FONT_CANDIDATES:
        for folder in dirs or FONT_DIRS:
            path = os.path.join(folder, regular)
            if os.path.isfile(path):
                bold_path = os.path.join(folder, bold)
                return path, bold_path if os.path.isfile(bold_path) else path
    return None


def _xml(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_pdf(content: DocumentContent, path: str, fonts: Optional[tuple[str, str]] = None) -> None:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    fonts = fonts or find_fonts()
    if fonts is None:
        raise RenderError("Не найден шрифт с кириллицей (Arial, Segoe UI, Calibri или DejaVu Sans)")
    pdfmetrics.registerFont(TTFont("ArcRegular", fonts[0]))
    pdfmetrics.registerFont(TTFont("ArcBold", fonts[1]))
    title = ParagraphStyle("t", fontName="ArcBold", fontSize=22, leading=27, spaceAfter=8,
                           textColor=colors.HexColor("#3b2a00"))
    subtitle = ParagraphStyle("s", fontName="ArcRegular", fontSize=13, leading=17, spaceAfter=12,
                              textColor=colors.HexColor("#555555"))
    heading = ParagraphStyle("h", fontName="ArcBold", fontSize=15, leading=19, spaceBefore=12, spaceAfter=6)
    body = ParagraphStyle("b", fontName="ArcRegular", fontSize=11, leading=15, spaceAfter=6)
    small = ParagraphStyle("sm", fontName="ArcRegular", fontSize=9, leading=12)

    story = [Paragraph(_xml(content.title), title)]
    if content.subtitle:
        story.append(Paragraph(_xml(content.subtitle), subtitle))
    if content.note:
        story.append(Paragraph(_xml(content.note), small))
    for section in content.sections:
        story.append(Paragraph(_xml(section.heading), heading))
        for paragraph in section.paragraphs:
            story.append(Paragraph(_xml(paragraph), body))
        if section.bullets:
            story.append(ListFlowable([ListItem(Paragraph(_xml(b), body), leftIndent=12) for b in section.bullets],
                                      bulletType="bullet", start="•", leftIndent=14))
    if content.table and content.table.rows:
        story.append(Paragraph("Таблица", heading))
        data = [[Paragraph(_xml(c), small) for c in content.table.columns]]
        data += [[Paragraph(_xml(v), small) for v in row] for row in content.table.normalized_rows()]
        table = Table(data, repeatRows=1)
        table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                                   ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#ffd27a")),
                                   ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        story.append(table)
    if content.sources:
        story.append(Paragraph("Источники", heading))
        for index, source in enumerate(content.sources, 1):
            story.append(Paragraph(f"{index}. {_xml(source.title)} — {_xml(source.url)}", small))
    story.append(Spacer(1, 0.5 * cm))
    doc = SimpleDocTemplate(path, pagesize=A4, title=content.title, author="A.R.C.",
                            leftMargin=2 * cm, rightMargin=2 * cm, topMargin=2 * cm, bottomMargin=2 * cm)
    doc.build(story)


def verify_pdf(content: DocumentContent, path: str) -> Verification:
    from pypdf import PdfReader

    with open(path, "rb") as fh:
        if fh.read(5) != b"%PDF-":
            return Verification(False, ["файл не является PDF"])
    reader = PdfReader(path)
    pages = len(reader.pages)
    text = _squash("".join(page.extract_text() or "" for page in reader.pages))
    details = []
    if pages < 1:
        details.append("в PDF нет страниц")
    if _squash(content.title)[:40] not in text:
        details.append("в тексте PDF нет заголовка")
    missing = [s.heading for s in content.sections if _squash(s.heading)[:40] not in text]
    if missing:
        details.append("нет разделов: " + ", ".join(missing[:3]))
    return Verification(not details, details, pages)


# ====================================================================== TXT
def render_txt(content: DocumentContent, path: str) -> None:
    lines = [content.title, "=" * min(len(content.title), 80)]
    if content.subtitle:
        lines.append(content.subtitle)
    if content.note:
        lines.append(f"({content.note})")
    for section in content.sections:
        lines += ["", section.heading, "-" * min(len(section.heading), 80)]
        lines += section.paragraphs
        lines += [f"  • {b}" for b in section.bullets]
    if content.table and content.table.rows:
        lines += ["", "Таблица", " | ".join(content.table.columns)]
        lines += [" | ".join(row) for row in content.table.normalized_rows()]
    if content.sources:
        lines += ["", "Источники"]
        lines += [f"{i}. {s.title} — {s.url}" for i, s in enumerate(content.sources, 1)]
    with open(path, "w", encoding="utf-8-sig", newline="\r\n") as fh:  # BOM: Notepad shows Cyrillic correctly
        fh.write("\n".join(lines) + "\n")


def verify_txt(content: DocumentContent, path: str) -> Verification:
    with open(path, encoding="utf-8-sig") as fh:
        text = fh.read()
    details = [] if content.title in text else ["нет заголовка"]
    missing = [s.heading for s in content.sections if s.heading not in text]
    if missing:
        details.append("нет разделов: " + ", ".join(missing[:3]))
    return Verification(not details, details, text.count("\n"))


RENDERERS: dict[str, tuple[Callable[[DocumentContent, str], None], Callable[[DocumentContent, str], Verification]]] = {
    "pptx": (render_pptx, verify_pptx),
    "docx": (render_docx, verify_docx),
    "xlsx": (render_xlsx, verify_xlsx),
    "pdf": (render_pdf, verify_pdf),
    "txt": (render_txt, verify_txt),
}
