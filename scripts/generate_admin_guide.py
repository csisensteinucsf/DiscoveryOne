#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import re
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from PIL import Image as PILImage
from reportlab.platypus import (
    HRFlowable,
    Image as FlowableImage,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    Preformatted,
    BaseDocTemplate,
    Frame,
    PageTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents


PAGE_WIDTH, PAGE_HEIGHT = letter
LEFT_MARGIN = 0.58 * inch
RIGHT_MARGIN = 0.58 * inch
TOP_MARGIN = 0.62 * inch
BOTTOM_MARGIN = 0.60 * inch
CONTENT_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN
BLUE = colors.HexColor('#12345B')
ACCENT = colors.HexColor('#1F6FA8')
MUTED = colors.HexColor('#53657A')
LIGHT_BLUE = colors.HexColor('#EAF2F8')
LIGHT_GRAY = colors.HexColor('#F3F5F7')
BORDER = colors.HexColor('#C7D2DE')


def build_styles():
    base = getSampleStyleSheet()
    return {
        'cover_title': ParagraphStyle(
            'GuideCoverTitle', parent=base['Title'], fontName='Helvetica-Bold',
            fontSize=23, leading=27, alignment=TA_LEFT, textColor=BLUE, spaceAfter=6,
        ),
        'cover_subtitle': ParagraphStyle(
            'GuideCoverSubtitle', parent=base['BodyText'], fontName='Helvetica',
            fontSize=11.5, leading=15, textColor=ACCENT, spaceAfter=10,
        ),
        'cover_body': ParagraphStyle(
            'GuideCoverBody', parent=base['BodyText'], fontName='Helvetica',
            fontSize=9.2, leading=12.5, textColor=colors.HexColor('#172230'), spaceAfter=8,
        ),
        'cover_meta': ParagraphStyle(
            'GuideCoverMeta', parent=base['BodyText'], fontName='Helvetica',
            fontSize=8.2, leading=11, textColor=MUTED, spaceAfter=2,
        ),
        'cover_label': ParagraphStyle(
            'GuideCoverLabel', parent=base['BodyText'], fontName='Helvetica-Bold',
            fontSize=8.5, leading=11, textColor=ACCENT, spaceAfter=3,
        ),
        'toc_title': ParagraphStyle(
            'GuideTOCTitle', parent=base['Heading1'], fontName='Helvetica-Bold',
            fontSize=18, leading=22, textColor=BLUE, spaceAfter=12,
        ),
        'toc_level_0': ParagraphStyle(
            'GuideTOCLevel0', parent=base['BodyText'], fontName='Helvetica-Bold',
            fontSize=8.2, leading=10.2, textColor=BLUE, leftIndent=0, firstLineIndent=0, spaceBefore=2,
        ),
        'toc_level_1': ParagraphStyle(
            'GuideTOCLevel1', parent=base['BodyText'], fontName='Helvetica',
            fontSize=7.5, leading=9.3, textColor=colors.HexColor('#172230'), leftIndent=14, firstLineIndent=0,
        ),
        'title': ParagraphStyle(
            'GuideTitle', parent=base['Title'], fontName='Helvetica-Bold',
            fontSize=22, leading=27, textColor=BLUE, spaceAfter=10,
        ),
        'subtitle': ParagraphStyle(
            'GuideSubtitle', parent=base['Heading2'], fontName='Helvetica',
            fontSize=12.5, leading=16, textColor=MUTED, spaceAfter=14,
        ),
        'part': ParagraphStyle(
            'GuidePart', parent=base['Heading1'], fontName='Helvetica-Bold',
            fontSize=18, leading=22, textColor=BLUE, spaceBefore=4, spaceAfter=11, keepWithNext=True,
        ),
        'h2': ParagraphStyle(
            'GuideH2', parent=base['Heading2'], fontName='Helvetica-Bold',
            fontSize=15.5, leading=19, textColor=BLUE, spaceBefore=10, spaceAfter=7, keepWithNext=True,
        ),
        'h3': ParagraphStyle(
            'GuideH3', parent=base['Heading3'], fontName='Helvetica-Bold',
            fontSize=11.5, leading=14, textColor=ACCENT, spaceBefore=8, spaceAfter=5, keepWithNext=True,
        ),
        'h4': ParagraphStyle(
            'GuideH4', parent=base['Heading4'], fontName='Helvetica-Bold',
            fontSize=9.7, leading=12, textColor=BLUE, spaceBefore=6, spaceAfter=4, keepWithNext=True,
        ),
        'body': ParagraphStyle(
            'GuideBody', parent=base['BodyText'], fontName='Helvetica',
            fontSize=8.6, leading=11.3, textColor=colors.HexColor('#172230'), spaceAfter=5,
        ),
        'small': ParagraphStyle(
            'GuideSmall', parent=base['BodyText'], fontName='Helvetica',
            fontSize=7.3, leading=9.3, textColor=colors.HexColor('#172230'),
        ),
        'table_header': ParagraphStyle(
            'GuideTableHeader', parent=base['BodyText'], fontName='Helvetica-Bold',
            fontSize=7.2, leading=8.7, textColor=colors.white,
        ),
        'table_cell': ParagraphStyle(
            'GuideTableCell', parent=base['BodyText'], fontName='Helvetica',
            fontSize=6.9, leading=8.5, textColor=colors.HexColor('#172230'),
        ),
        'quote': ParagraphStyle(
            'GuideQuote', parent=base['BodyText'], fontName='Helvetica',
            fontSize=8.2, leading=11, textColor=BLUE, leftIndent=8, rightIndent=8,
        ),
        'code': ParagraphStyle(
            'GuideCode', parent=base['Code'], fontName='Courier',
            fontSize=7.1, leading=9.1, textColor=colors.HexColor('#172230'),
            leftIndent=7, rightIndent=7, spaceBefore=3, spaceAfter=6,
        ),
    }


def inline_markup(value: str) -> str:
    tokens: list[str] = []

    def hold_code(match):
        tokens.append(f"<font name='Courier'>{html.escape(match.group(1))}</font>")
        return f'@@CODE{len(tokens) - 1}@@'

    value = re.sub(r'`([^`]+)`', hold_code, value)
    value = html.escape(value, quote=False)
    value = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', value)
    value = re.sub(
        r'\[([^\]]+)\]\((https?://[^)]+)\)',
        lambda m: f"<link href='{html.escape(m.group(2), quote=True)}' color='#1F6FA8'>{m.group(1)}</link>",
        value,
    )
    value = re.sub(
        r'(?<![\"\'=])(https?://[^\s<]+)',
        lambda m: f"<link href='{html.escape(m.group(1), quote=True)}' color='#1F6FA8'>{m.group(1)}</link>",
        value,
    )
    for index, token in enumerate(tokens):
        value = value.replace(f'@@CODE{index}@@', token)
    return value


def is_table_separator(line: str) -> bool:
    cells = [cell.strip() for cell in line.strip().strip('|').split('|')]
    return bool(cells) and all(re.fullmatch(r':?-{3,}:?', cell or '') for cell in cells)


def parse_table(lines: list[str], styles):
    rows = [[cell.strip() for cell in line.strip().strip('|').split('|')] for line in lines]
    if len(rows) >= 2 and is_table_separator(lines[1]):
        rows.pop(1)
    column_count = max(len(row) for row in rows)
    for row in rows:
        row.extend([''] * (column_count - len(row)))
    weights = []
    for column in range(column_count):
        longest = max(len(re.sub(r'[`*]', '', row[column])) for row in rows)
        weights.append(max(12, min(longest, 45)))
    total = sum(weights)
    widths = [CONTENT_WIDTH * weight / total for weight in weights]
    data = []
    for row_index, row in enumerate(rows):
        style = styles['table_header'] if row_index == 0 else styles['table_cell']
        data.append([Paragraph(inline_markup(cell), style) for cell in row])
    table = Table(data, colWidths=widths, repeatRows=1, hAlign='LEFT')
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), BLUE),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('GRID', (0, 0), (-1, -1), 0.35, BORDER),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, LIGHT_GRAY]),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    return table


def quote_box(text: str, styles):
    table = Table([[Paragraph(inline_markup(text), styles['quote'])]], colWidths=[CONTENT_WIDTH])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), LIGHT_BLUE),
        ('BOX', (0, 0), (-1, -1), 0.6, ACCENT),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    return table


def optimized_logo(path: Path) -> BytesIO:
    buffer = BytesIO()
    with PILImage.open(path) as source:
        image = source.convert('RGBA')
        image.thumbnail((256, 256), PILImage.Resampling.LANCZOS)
        background = PILImage.new('RGBA', image.size, (255, 255, 255, 255))
        background.alpha_composite(image)
        background.convert('RGB').save(buffer, format='JPEG', quality=88, optimize=True)
    buffer.seek(0)
    return buffer


def front_matter_value(markdown_text: str, label: str, fallback: str) -> str:
    match = re.search(rf'^\*\*{re.escape(label)}:\*\*\s*(.+?)\s*$', markdown_text, flags=re.MULTILINE)
    return match.group(1).strip() if match else fallback


def cover_story(markdown_text: str, styles, logo_path: Path):
    guide_date = front_matter_value(markdown_text, 'Guide date', 'August 2026')
    repository = front_matter_value(markdown_text, 'Repository', 'https://github.com/csisensteinucsf/DiscoveryOne')
    release_match = re.search(
        r'^>\s*\*\*Release posture:\*\*\s*(.+?)\s*$',
        markdown_text,
        flags=re.MULTILINE,
    )
    release_posture = release_match.group(1).strip() if release_match else (
        'Treat this build as a pilot release and validate it in a non-production environment before using it for active legal matters.'
    )

    story = [Spacer(1, 0.12 * inch)]
    if logo_path.exists():
        logo = FlowableImage(optimized_logo(logo_path), width=0.58 * inch, height=0.58 * inch)
        logo.hAlign = 'CENTER'
        story.extend([logo, Spacer(1, 0.28 * inch)])
    story.extend([
        Paragraph('DiscoveryOne Universal', styles['cover_title']),
        Paragraph(
            'Administrator Installation, Configuration, Integration, and Operations Guide',
            styles['cover_subtitle'],
        ),
        HRFlowable(width='100%', thickness=1.5, color=ACCENT),
        Spacer(1, 0.22 * inch),
        Paragraph(
            'A step-by-step guide from repository access through a production-ready deployment, including first-time setup, TLS, backups, security controls, and every supported or planned integration.',
            styles['cover_body'],
        ),
        Spacer(1, 0.08 * inch),
        Paragraph(inline_markup(f'**Guide date:** {guide_date}'), styles['cover_meta']),
        Paragraph(inline_markup(f'**Repository:** {repository}'), styles['cover_meta']),
        Paragraph(inline_markup('**Release status:** Pilot / collaborative deployment'), styles['cover_meta']),
        Spacer(1, 0.72 * inch),
        Paragraph('Important', styles['cover_label']),
        quote_box(f'**Release posture:** {release_posture}', styles),
    ])
    return story

def markdown_story(markdown_text: str, styles, first_heading: bool = True):
    lines = markdown_text.replace('\r\n', '\n').split('\n')
    story = []
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        stripped = line.strip()
        if not stripped:
            index += 1
            continue
        if stripped == '<!-- PAGEBREAK -->':
            story.append(PageBreak())
            index += 1
            continue
        if stripped.startswith('```'):
            index += 1
            code_lines = []
            while index < len(lines) and not lines[index].strip().startswith('```'):
                code_lines.append(lines[index].rstrip())
                index += 1
            index += 1
            story.append(Preformatted('\n'.join(code_lines), styles['code'], maxLineLength=96))
            continue
        if stripped.startswith('|') and index + 1 < len(lines) and is_table_separator(lines[index + 1]):
            table_lines = [line, lines[index + 1].rstrip()]
            index += 2
            while index < len(lines) and lines[index].strip().startswith('|'):
                table_lines.append(lines[index].rstrip())
                index += 1
            story.extend([parse_table(table_lines, styles), Spacer(1, 6)])
            continue
        heading = re.match(r'^(#{1,4})\s+(.+)$', stripped)
        if heading:
            level = len(heading.group(1))
            text = inline_markup(heading.group(2))
            if level == 1 and first_heading:
                style = styles['title']
                first_heading = False
            elif level == 1:
                style = styles['part']
            elif level == 2 and first_heading:
                style = styles['subtitle']
                first_heading = False
            else:
                style = styles[{2: 'h2', 3: 'h3', 4: 'h4'}[level]]
            story.append(Paragraph(text, style))
            index += 1
            continue
        if stripped.startswith('> '):
            quote_lines = []
            while index < len(lines) and lines[index].strip().startswith('>'):
                quote_lines.append(lines[index].strip().lstrip('>').strip())
                index += 1
            story.extend([quote_box(' '.join(quote_lines), styles), Spacer(1, 6)])
            continue
        bullet = re.match(r'^[-*]\s+(.+)$', stripped)
        numbered = re.match(r'^\d+\.\s+(.+)$', stripped)
        if bullet or numbered:
            ordered = bool(numbered)
            items = []
            pattern = r'^\d+\.\s+(.+)$' if ordered else r'^[-*]\s+(.+)$'
            while index < len(lines):
                match = re.match(pattern, lines[index].strip())
                if not match:
                    break
                value = match.group(1)
                if value.startswith('[ ] '):
                    value = '[ ] ' + value[4:]
                elif value.lower().startswith('[x] '):
                    value = '[x] ' + value[4:]
                items.append(ListItem(Paragraph(inline_markup(value), styles['body']), leftIndent=12))
                index += 1
            story.append(ListFlowable(
                items, bulletType='1' if ordered else 'bullet', start='1',
                leftIndent=18, bulletFontName='Helvetica', bulletFontSize=7.5,
                bulletColor=BLUE, spaceAfter=4,
            ))
            continue
        if stripped == '---':
            story.extend([Spacer(1, 3), HRFlowable(width='100%', thickness=0.7, color=BORDER), Spacer(1, 4)])
            index += 1
            continue
        paragraph_lines = [stripped]
        index += 1
        while index < len(lines):
            candidate = lines[index].strip()
            if not candidate:
                break
            if (
                candidate == '<!-- PAGEBREAK -->'
                or candidate.startswith('#')
                or candidate.startswith('```')
                or candidate.startswith('>')
                or candidate.startswith('|')
                or re.match(r'^[-*]\s+', candidate)
                or re.match(r'^\d+\.\s+', candidate)
                or candidate == '---'
            ):
                break
            paragraph_lines.append(candidate)
            index += 1
        story.append(Paragraph(inline_markup(' '.join(paragraph_lines)), styles['body']))
    return story


class GuideDocTemplate(BaseDocTemplate):
    def beforeDocument(self):
        super().beforeDocument()
        self._toc_counter = 0

    def afterFlowable(self, flowable):
        if not isinstance(flowable, Paragraph):
            return
        level_by_style = {
            'GuidePart': 0,
            'GuideH2': 0,
            'GuideH3': 1,
        }
        level = level_by_style.get(flowable.style.name)
        if level is None:
            return
        title = flowable.getPlainText()
        counter = getattr(self, '_toc_counter', 0) + 1
        self._toc_counter = counter
        key = f'guide-heading-{counter}'
        self.canv.bookmarkPage(key)
        self.canv.addOutlineEntry(title, key, level=level, closed=False)
        self.notify('TOCEntry', (level, title, self.page, key))


def table_of_contents_story(styles):
    toc = TableOfContents()
    toc.levelStyles = [styles['toc_level_0'], styles['toc_level_1']]
    toc.dotsMinLevel = 0
    return [Paragraph('Table of Contents', styles['toc_title']), toc]

def footer(canvas, doc):
    canvas.saveState()
    canvas.setStrokeColor(BORDER)
    canvas.setLineWidth(0.6)
    y = 0.40 * inch
    canvas.line(LEFT_MARGIN, y + 11, PAGE_WIDTH - RIGHT_MARGIN, y + 11)
    canvas.setFont('Helvetica', 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(LEFT_MARGIN, y, 'DiscoveryOne Universal Administrator Guide')
    canvas.drawRightString(PAGE_WIDTH - RIGHT_MARGIN, y, f'Page {doc.page}')
    canvas.restoreState()


def generate(source: Path, output: Path):
    styles = build_styles()
    markdown_text = source.read_text(encoding='utf-8')
    marker = '<!-- PAGEBREAK -->'
    if marker in markdown_text:
        _front_matter, body = markdown_text.split(marker, 1)
        logo_path = source.parents[2] / 'frontend' / 'public' / 'img' / 'D1_Logo.png'
        story = cover_story(markdown_text, styles, logo_path)
        story.extend([PageBreak(), *table_of_contents_story(styles), PageBreak()])
        story.extend(markdown_story(body.lstrip(), styles, first_heading=False))
    else:
        story = [*table_of_contents_story(styles), PageBreak(), *markdown_story(markdown_text, styles)]
    output.parent.mkdir(parents=True, exist_ok=True)
    doc = GuideDocTemplate(
        str(output), pagesize=letter,
        leftMargin=LEFT_MARGIN, rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN, bottomMargin=BOTTOM_MARGIN,
        title='DiscoveryOne Universal Administrator Guide',
        author='DiscoveryOne', subject='Installation, configuration, integrations, and operations',
    )
    frame = Frame(
        doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
        leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0,
        id='guide-frame',
    )
    doc.addPageTemplates([PageTemplate(id='guide-pages', frames=[frame], onPage=footer)])
    doc.multiBuild(story)

def main():
    parser = argparse.ArgumentParser(description='Generate the DiscoveryOne administrator guide PDF.')
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    generate(args.source, args.output)


if __name__ == '__main__':
    main()

