"""Render report Markdown as a standalone, paginated PDF."""
from html import escape
from html.parser import HTMLParser
from io import BytesIO

import markdown
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pathlib import Path
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Preformatted


class _Node:
    def __init__(self, tag='root'):
        self.tag, self.children = tag, []


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node()
        self.stack = [self.root]

    def handle_starttag(self, tag, attrs):
        node = _Node(tag)
        self.stack[-1].children.append(node)
        if tag not in ('br', 'hr', 'img', 'meta', 'link', 'input'):
            self.stack.append(node)

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i].tag == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def _inline(node):
    if isinstance(node, str):
        return escape(node).replace('\n', ' ')
    if node.tag in ('script', 'style', 'iframe', 'object'):
        return ''
    content = ''.join(_inline(c) for c in node.children)
    if node.tag == 'br':
        return '<br/>'
    if node.tag in ('strong', 'b'):
        return f'<b>{content}</b>'
    if node.tag in ('em', 'i'):
        return f'<i>{content}</i>'
    return content


def _descendants(node, tag):
    if not isinstance(node, _Node):
        return
    if node.tag == tag:
        yield node
    else:
        for child in node.children:
            yield from _descendants(child, tag)


def render_report_pdf(text: str, title: str) -> bytes:
    tree = _Tree()
    tree.feed(markdown.markdown(text, extensions=['tables', 'fenced_code', 'sane_lists']))
    # Embed a Unicode font where available; ReportLab bundles Vera as a fallback.
    font_dir = Path('/usr/share/fonts/truetype/dejavu')
    regular = font_dir / 'DejaVuSans.ttf'
    bold = font_dir / 'DejaVuSans-Bold.ttf'
    if not (regular.is_file() and bold.is_file()):
        import reportlab
        font_dir = Path(reportlab.__file__).parent / 'fonts'
        regular, bold = font_dir / 'Vera.ttf', font_dir / 'VeraBd.ttf'
    pdfmetrics.registerFont(TTFont('ArgusReport', str(regular)))
    pdfmetrics.registerFont(TTFont('ArgusReport-Bold', str(bold)))
    pdfmetrics.registerFontFamily('ArgusReport', normal='ArgusReport', bold='ArgusReport-Bold', italic='ArgusReport', boldItalic='ArgusReport-Bold')
    styles = getSampleStyleSheet()
    for name in ('Heading1', 'Heading2', 'Heading3'):
        styles[name].fontName = 'ArgusReport-Bold'
    styles.add(ParagraphStyle(name='ReportBody', parent=styles['BodyText'], fontName='ArgusReport', fontSize=9, leading=13, spaceAfter=6, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='ReportCell', parent=styles['ReportBody'], fontSize=7, leading=9, spaceAfter=0, wordWrap='CJK'))
    styles.add(ParagraphStyle(name='ReportEntry', parent=styles['ReportBody'], fontName='ArgusReport-Bold', fontSize=10, leading=14, spaceBefore=8, spaceAfter=3, textColor=colors.HexColor('#263b4a'), keepWithNext=True))
    styles.add(ParagraphStyle(name='ReportField', parent=styles['ReportBody'], leftIndent=10, firstLineIndent=-10, spaceAfter=3))
    styles.add(ParagraphStyle(name='ReportHeader', parent=styles['ReportCell'], fontName='ArgusReport-Bold', textColor=colors.white))
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, leftMargin=14*mm, rightMargin=14*mm, topMargin=16*mm, bottomMargin=15*mm, title=title)
    story = []

    def add(node, level=0):
        if isinstance(node, str):
            if node.strip():
                story.append(Paragraph(escape(node), styles['ReportBody']))
            return
        tag = node.tag
        if tag in ('script', 'style', 'iframe', 'object'):
            return
        if tag == 'table':
            rows = []
            for row in _descendants(node, 'tr'):
                cells = [c for c in row.children if isinstance(c, _Node) and c.tag in ('th', 'td')]
                if cells:
                    rows.append(cells)
            if rows:
                count = max(map(len, rows))
                # Wide tables and prose-heavy cells become labelled entries. This
                # keeps every field readable on portrait pages and lets long
                # rationales flow naturally across page breaks.
                prose = any(len(''.join(_plain(cell)).strip()) > 90 for row in rows[1:] for cell in row)
                if count > 4 or prose:
                    headers = rows[0]
                    for index, row in enumerate(rows[1:], 1):
                        story.append(Paragraph(f'Entry {index}', styles['ReportEntry']))
                        for column, cell in enumerate(row):
                            label = _inline(headers[column]).strip() if column < len(headers) else f'Field {column + 1}'
                            value = _inline(cell).strip() or '—'
                            story.append(Paragraph(f'&#8226; <b>{label or f"Field {column + 1}"}:</b> {value}', styles['ReportField']))
                        story.append(Spacer(1, 4))
                else:
                    formatted = []
                    for row in rows:
                        cells = [Paragraph(_inline(c) or ' ', styles['ReportHeader' if c.tag == 'th' else 'ReportCell']) for c in row]
                        cells.extend([''] * (count - len(cells)))
                        formatted.append(cells)
                    table = Table(formatted, colWidths=[doc.width / count]*count, repeatRows=1, splitByRow=1, splitInRow=1, hAlign='LEFT')
                    table.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), colors.HexColor('#263b4a')), ('GRID', (0,0), (-1,-1), .35, colors.HexColor('#cbd5dc')), ('VALIGN', (0,0), (-1,-1), 'TOP'), ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f3f6f8')]), ('LEFTPADDING', (0,0), (-1,-1), 4), ('RIGHTPADDING', (0,0), (-1,-1), 4)]))
                    story.extend([table, Spacer(1, 8)])
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            style = styles['Heading1' if tag == 'h1' else 'Heading2' if tag == 'h2' else 'Heading3']
            story.append(Paragraph(_inline(node) or ' ', style))
        elif tag in ('p', 'li'):
            story.append(Paragraph(('&#8226; ' if tag == 'li' else '') + (_inline(node) or ' '), styles['ReportBody']))
        elif tag == 'pre':
            story.append(Preformatted(''.join(_plain(node)).strip(), styles['Code']))
        elif tag == 'hr':
            story.append(Spacer(1, 8))
        else:
            for child in node.children:
                add(child, level+1)

    for child in tree.root.children:
        add(child)
    if not story:
        story.append(Paragraph('No report content available.', styles['ReportBody']))

    def footer(canvas, document):
        canvas.setFont('ArgusReport', 8)
        canvas.setFillColor(colors.HexColor('#596c78'))
        canvas.drawString(document.leftMargin, 8*mm, title)
        canvas.drawRightString(document.pagesize[0] - document.rightMargin, 8*mm, str(document.page))

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return output.getvalue()


def _plain(node):
    if isinstance(node, str):
        yield node
    else:
        for child in node.children:
            yield from _plain(child)
