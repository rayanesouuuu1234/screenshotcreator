"""Word document export for chronological screenshots."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_LINE_SPACING
from docx.shared import Inches, Pt, RGBColor

OUTPUT_DIR = Path("outputs")
PAGE_IMAGE_WIDTH = Inches(6.5)
TRANSCRIPT_FONT_SIZE = Pt(10)
LABEL_FONT_SIZE = Pt(14)


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem or "video"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return stem or "video"


def default_docx_name(video_filename: str) -> str:
    return f"{_safe_stem(video_filename)}_{date.today().isoformat()}.docx"


def _segment_text(segment: dict) -> str:
    return str(segment.get("text", "")).strip()


def _segments_for_window(segments: list[dict], start: float, end: float | None) -> list[str]:
    lines: list[str] = []
    for segment in segments:
        text = _segment_text(segment)
        if not text:
            continue
        segment_start = float(segment.get("start", 0.0) or 0.0)
        if segment_start < start:
            continue
        if end is not None and segment_start >= end:
            continue
        lines.append(text)
    return lines


def _add_horizontal_rule(doc: Document) -> None:
    paragraph = doc.add_paragraph()
    run = paragraph.add_run("─" * 72)
    run.font.color.rgb = RGBColor(221, 221, 221)


def _add_transcript_block(doc: Document, lines: list[str]) -> None:
    if not lines:
        return
    _add_horizontal_rule(doc)
    paragraph = doc.add_paragraph()
    paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
    paragraph.paragraph_format.space_after = Pt(10)
    run = paragraph.add_run("\n".join(lines))
    run.italic = True
    run.font.size = TRANSCRIPT_FONT_SIZE
    run.font.color.rgb = RGBColor(102, 102, 102)
    _add_horizontal_rule(doc)


def _add_ai_instructions(doc: Document, ai_instructions: str) -> None:
    instructions = ai_instructions.strip()
    if not instructions:
        return
    doc.add_page_break()
    heading = doc.add_heading("AI Instructions for Functional Design Document", level=1)
    heading.runs[0].font.size = Pt(20)
    for paragraph_text in instructions.splitlines():
        text = paragraph_text.strip()
        if not text:
            doc.add_paragraph()
            continue
        paragraph = doc.add_paragraph(text)
        paragraph.paragraph_format.space_after = Pt(6)
        if paragraph.runs:
            paragraph.runs[0].font.size = Pt(11)
            paragraph.runs[0].font.color.rgb = RGBColor(68, 68, 68)


def create_screenshots_docx(
    screenshots: list[dict],
    *,
    video_filename: str,
    output_path: str | Path | None = None,
    transcript_segments: list[dict] | None = None,
    ai_instructions: str = "",
) -> Path:
    """Create a Word document with timestamped screenshots and paired transcript text."""
    if not screenshots:
        raise ValueError("No screenshots were generated, so a document cannot be created.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(output_path) if output_path else OUTPUT_DIR / default_docx_name(video_filename)

    doc = Document()
    transcript_segments = transcript_segments or []
    rendered = 0

    for index, shot in enumerate(screenshots, start=1):
        image_path = Path(str(shot.get("path", "")))
        if not image_path.is_file():
            continue

        label = str(shot.get("label", "00:00:00"))
        heading = doc.add_heading(f"{index}. {label}", level=2)
        if heading.runs:
            heading.runs[0].font.size = LABEL_FONT_SIZE

        doc.add_picture(str(image_path), width=PAGE_IMAGE_WIDTH)

        screenshot_start = float(shot.get("timestamp", 0.0) or 0.0)
        next_timestamp = None
        if index < len(screenshots):
            next_timestamp = float(
                screenshots[index].get("timestamp", screenshot_start) or screenshot_start
            )

        transcript_lines = _segments_for_window(
            transcript_segments,
            screenshot_start,
            next_timestamp,
        )
        _add_transcript_block(doc, transcript_lines)
        rendered += 1

    if rendered == 0:
        raise ValueError("None of the generated screenshot files could be read.")

    _add_ai_instructions(doc, ai_instructions)
    doc.save(out)
    return out


# Backward-compatible alias while older code paths may still import the PDF helper name.
create_screenshots_pdf = create_screenshots_docx
_default_pdf_name = default_docx_name
