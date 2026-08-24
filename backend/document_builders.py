"""PPTX/DOCX/Markdown file builders for the Document Generator -- split out
of document_generator.py purely to stay under the house 500-line cap. No
behaviour changed in the move (see git history for the original code).

These functions are pure: given already-generated, already-capped
structured content (a dict with `title`/`slides`/`sections`, produced by
document_ai.generate_content) they write bytes to disk. They have no
knowledge of gating, billing, or the upstream model call -- all of that
lives in document_generator.py's `/v1/documents/generate` handler, which
calls these only AFTER a document has already been billed for.

No external module imports anything from here directly (grepped
2026-08-24: only document_generator.py does); nothing here needs a
monkeypatch contract.
"""
from __future__ import annotations

from pathlib import Path


def _escape_mdx_text(text: str) -> str:
    """Escape text destined for a Markdown slide deck."""
    if not isinstance(text, str):
        text = str(text)
    # Escape HTML tags and common Markdown link injection
    return (text.replace('&', '&amp;').replace('<', '&lt;')
                .replace('>', '&gt;'))


def _create_pptx(data: dict, output_path: Path) -> None:
    """Create a PowerPoint file from structured data."""
    from pptx import Presentation
    from pptx.util import Inches, Pt, Emu
    from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    from pptx.dml.color import RGBColor

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    # Color scheme
    PRIMARY = RGBColor(0x25, 0x63, 0xEB)    # Blue
    DARK = RGBColor(0x1E, 0x29, 0x3B)       # Dark navy
    LIGHT = RGBColor(0xF8, 0xFA, 0xFC)      # Light gray
    WHITE = RGBColor(0xFF, 0xFF, 0xFF)
    ACCENT = RGBColor(0x10, 0xB9, 0x81)     # Green

    def add_bg(slide, color):
        bg = slide.background
        fill = bg.fill
        fill.solid()
        fill.fore_color.rgb = color

    # Title slide
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # Blank
    add_bg(slide, DARK)

    # Title
    left, top, width, height = Inches(1), Inches(2), Inches(11), Inches(2)
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = data.get('title', 'Presentation')
    p.font.size = Pt(44)
    p.font.bold = True
    p.font.color.rgb = WHITE
    p.alignment = PP_ALIGN.CENTER

    # Subtitle
    if data.get('subtitle'):
        left, top, width, height = Inches(2), Inches(4.2), Inches(9), Inches(1)
        txBox = slide.shapes.add_textbox(left, top, width, height)
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = data['subtitle']
        p.font.size = Pt(20)
        p.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)
        p.alignment = PP_ALIGN.CENTER

    # Content slides
    for i, slide_data in enumerate(data.get('slides', [])):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        add_bg(slide, WHITE)

        # Slide number
        txBox = slide.shapes.add_textbox(Inches(12), Inches(0.3), Inches(1), Inches(0.5))
        tf = txBox.text_frame
        p = tf.paragraphs[0]
        p.text = str(i + 2)
        p.font.size = Pt(14)
        p.font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)
        p.alignment = PP_ALIGN.RIGHT

        # Accent bar
        from pptx.util import Emu
        shape = slide.shapes.add_shape(
            1, Inches(0.5), Inches(0.8), Inches(0.08), Inches(0.6)
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = PRIMARY
        shape.line.fill.background()

        # Title
        txBox = slide.shapes.add_textbox(Inches(0.8), Inches(0.7), Inches(11), Inches(0.8))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = slide_data.get('title', f'Slide {i+2}')
        p.font.size = Pt(32)
        p.font.bold = True
        p.font.color.rgb = DARK

        # Content bullets
        txBox = slide.shapes.add_textbox(Inches(0.8), Inches(1.8), Inches(11), Inches(5))
        tf = txBox.text_frame
        tf.word_wrap = True
        content_items = slide_data.get('content', [])
        for j, item in enumerate(content_items):
            if j == 0:
                p = tf.paragraphs[0]
            else:
                p = tf.add_paragraph()
            p.text = f"  •  {item}"
            p.font.size = Pt(18)
            p.font.color.rgb = RGBColor(0x33, 0x41, 0x55)
            p.space_after = Pt(12)

        # Speaker notes
        if slide_data.get('notes'):
            notes_slide = slide.notes_slide
            notes_slide.notes_text_frame.text = slide_data['notes']

    # Thank you slide
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide, PRIMARY)
    txBox = slide.shapes.add_textbox(Inches(1), Inches(2.5), Inches(11), Inches(2))
    tf = txBox.text_frame
    p = tf.paragraphs[0]
    p.text = 'Thank You! 🙏'
    p.font.size = Pt(48)
    p.font.bold = True
    p.font.color.rgb = WHITE
    p.alignment = PP_ALIGN.CENTER

    prs.save(str(output_path))


def _create_docx(data: dict, output_path: Path) -> None:
    """Create a Word document from structured data."""
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.style import WD_STYLE_TYPE

    doc = Document()

    # Style setup
    style = doc.styles['Normal']
    font = style.font
    font.size = Pt(11)
    font.name = 'Arial'

    # Title
    title = doc.add_heading(data.get('title', 'Document'), level=0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    if data.get('subtitle'):
        subtitle = doc.add_paragraph(data['subtitle'])
        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
        subtitle.runs[0].font.size = Pt(14)
        subtitle.runs[0].font.color.rgb = RGBColor(0x64, 0x74, 0x8B)

    doc.add_paragraph('')  # Spacer

    # Sections
    for section_data in data.get('sections', []):
        doc.add_heading(section_data.get('heading', 'Section'), level=1)

        if section_data.get('content'):
            doc.add_paragraph(section_data['content'])

        for subsection in section_data.get('subsections', []):
            doc.add_heading(subsection.get('heading', ''), level=2)
            if subsection.get('content'):
                doc.add_paragraph(subsection['content'])

    # Footer
    doc.add_paragraph('')
    footer = doc.add_paragraph('Generated by Sanjabai — sanjabai.ir')
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer.runs[0].font.size = Pt(9)
    footer.runs[0].font.color.rgb = RGBColor(0x94, 0xA3, 0xB8)

    doc.save(str(output_path))


def _create_mdx(data: dict, output_path: Path) -> None:
    """Create a Markdown slide deck (compatible with Marp/reveal.js)."""
    lines = []

    # Title slide
    lines.append('---')
    lines.append(f'# {data.get("title", "Presentation")}')
    if data.get('subtitle'):
        lines.append(f'\n### {data["subtitle"]}')
    lines.append('\n---\n')

    # Content slides
    for slide_data in data.get('slides', []):
        lines.append('---')
        lines.append(f'\n## {_escape_mdx_text(slide_data.get("title", "Slide"))}\n')
        for item in slide_data.get('content', []):
            lines.append(f'- {_escape_mdx_text(item)}')
        if slide_data.get('notes'):
            lines.append(f'\n<!-- Notes: {_escape_mdx_text(slide_data["notes"])} -->')
        lines.append('')

    # End
    lines.append('---')
    lines.append('\n# Thank You! 🙏')
    lines.append('\n---')

    output_path.write_text('\n'.join(lines), encoding='utf-8')
