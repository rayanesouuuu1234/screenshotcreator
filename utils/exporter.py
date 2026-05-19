"""PDF export for chronological screenshots."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

PDF_DIR = Path("outputs")
PDF_PATH = PDF_DIR / "screenshots.pdf"
PAGE_WIDTH = 1280
TOP_PADDING = 24
LABEL_HEIGHT = 30
LABEL_GAP = 12
BOTTOM_PADDING = 16
DIVIDER_WIDTH = 1
TEXT_MARGIN_X = 24
TRANSCRIPT_RULE_GAP = 12
TRANSCRIPT_PADDING_Y = 10
TRANSCRIPT_FONT_SIZE = 16
TRANSCRIPT_LINE_GAP = 6
TRANSCRIPT_BLOCK_GAP = 14
INSTRUCTIONS_MARGIN = 64
INSTRUCTIONS_TITLE_SIZE = 30
INSTRUCTIONS_BODY_SIZE = 18
INSTRUCTIONS_LINE_GAP = 8


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem or "video"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return stem or "video"


def _default_pdf_name(video_filename: str) -> str:
    return f"{_safe_stem(video_filename)}_{date.today().isoformat()}.pdf"


def _font(size: int, *, italic: bool = False) -> ImageFont.ImageFont:
    candidates = (
        (
            "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
            "/Library/Fonts/Arial Italic.ttf",
        )
        if italic
        else (
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/Library/Fonts/Arial.ttf",
        )
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


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


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return []

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _text_width(candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def _text_width(text: str, font: ImageFont.ImageFont) -> int:
    left, _, right, _ = font.getbbox(text)
    return right - left


def _line_height(font: ImageFont.ImageFont) -> int:
    _, top, _, bottom = font.getbbox("Ag")
    return bottom - top


def _create_ai_instructions_page(ai_instructions: str) -> Image.Image | None:
    instructions = ai_instructions.strip()
    if not instructions:
        return None

    title_font = _font(INSTRUCTIONS_TITLE_SIZE)
    body_font = _font(INSTRUCTIONS_BODY_SIZE)
    max_width = PAGE_WIDTH - (INSTRUCTIONS_MARGIN * 2)
    body_lines: list[str] = []
    for paragraph in instructions.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            body_lines.append("")
            continue
        body_lines.extend(_wrap_text(paragraph, body_font, max_width))

    title_height = _line_height(title_font)
    body_line_height = _line_height(body_font) + INSTRUCTIONS_LINE_GAP
    page_height = max(
        720,
        INSTRUCTIONS_MARGIN * 2 + title_height + 34 + len(body_lines) * body_line_height,
    )
    page = Image.new("RGB", (PAGE_WIDTH, page_height), "white")
    draw = ImageDraw.Draw(page)
    y = INSTRUCTIONS_MARGIN
    draw.text((INSTRUCTIONS_MARGIN, y), "AI Instructions for Functional Design Document", fill="#111111", font=title_font)
    y += title_height + 34
    for line in body_lines:
        if line:
            draw.text((INSTRUCTIONS_MARGIN, y), line, fill="#444444", font=body_font)
        y += body_line_height
    return page


def create_screenshots_pdf(
    screenshots: list[dict],
    *,
    video_filename: str,
    output_path: str | Path | None = None,
    transcript_segments: list[dict] | None = None,
    ai_instructions: str = "",
) -> Path:
    """Create a full-width sequential PDF with timestamp-labeled screenshots."""
    if not screenshots:
        raise ValueError("No screenshots were generated, so a PDF cannot be created.")

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(output_path) if output_path else PDF_DIR / _default_pdf_name(video_filename)

    pages: list[Image.Image] = []
    label_font = _font(22)
    transcript_font = _font(TRANSCRIPT_FONT_SIZE, italic=True)
    transcript_segments = transcript_segments or []
    transcript_max_width = PAGE_WIDTH - (TEXT_MARGIN_X * 2)

    for index, shot in enumerate(screenshots, start=1):
        image_path = Path(str(shot.get("path", "")))
        if not image_path.is_file():
            continue

        with Image.open(image_path) as screenshot:
            screenshot = screenshot.convert("RGB")
            width, height = screenshot.size
            if width <= 0 or height <= 0:
                continue

            scale = PAGE_WIDTH / width
            image_height = max(1, int(height * scale))
            resized = screenshot.resize((PAGE_WIDTH, image_height), Image.Resampling.LANCZOS)

        image_y = TOP_PADDING + LABEL_HEIGHT + LABEL_GAP
        screenshot_start = float(shot.get("timestamp", 0.0) or 0.0)
        next_timestamp = None
        if index < len(screenshots):
            next_timestamp = float(screenshots[index].get("timestamp", screenshot_start) or screenshot_start)

        transcript_lines: list[str] = []
        for segment_text in _segments_for_window(transcript_segments, screenshot_start, next_timestamp):
            transcript_lines.extend(_wrap_text(segment_text, transcript_font, transcript_max_width))

        line_height = _line_height(transcript_font) + TRANSCRIPT_LINE_GAP
        transcript_height = 0
        if transcript_lines:
            transcript_height = (
                TRANSCRIPT_BLOCK_GAP
                + TRANSCRIPT_RULE_GAP
                + TRANSCRIPT_PADDING_Y
                + len(transcript_lines) * line_height
                + TRANSCRIPT_PADDING_Y
                + TRANSCRIPT_RULE_GAP
            )

        page_height = image_y + image_height + transcript_height + BOTTOM_PADDING
        page = Image.new("RGB", (PAGE_WIDTH, page_height), "white")
        draw = ImageDraw.Draw(page)
        label = str(shot.get("label", "00:00:00"))
        draw.text((24, TOP_PADDING), f"{index}. {label}", fill="#111111", font=label_font)
        page.paste(resized, (0, image_y))

        if transcript_lines:
            block_top = image_y + image_height + TRANSCRIPT_BLOCK_GAP
            draw.line(
                [(TEXT_MARGIN_X, block_top), (PAGE_WIDTH - TEXT_MARGIN_X, block_top)],
                fill="#DDDDDD",
                width=DIVIDER_WIDTH,
            )
            text_y = block_top + TRANSCRIPT_RULE_GAP + TRANSCRIPT_PADDING_Y
            for line in transcript_lines:
                draw.text((TEXT_MARGIN_X, text_y), line, fill="#666666", font=transcript_font)
                text_y += line_height
            bottom_rule_y = text_y + TRANSCRIPT_PADDING_Y
            draw.line(
                [(TEXT_MARGIN_X, bottom_rule_y), (PAGE_WIDTH - TEXT_MARGIN_X, bottom_rule_y)],
                fill="#DDDDDD",
                width=DIVIDER_WIDTH,
            )

        draw.line(
            [(0, page_height - BOTTOM_PADDING // 2), (PAGE_WIDTH, page_height - BOTTOM_PADDING // 2)],
            fill="#DDDDDD",
            width=DIVIDER_WIDTH,
        )
        pages.append(page)

    if not pages:
        raise ValueError("None of the generated screenshot files could be read.")

    instructions_page = _create_ai_instructions_page(ai_instructions)
    if instructions_page is not None:
        pages.append(instructions_page)

    pages[0].save(
        out,
        format="PDF",
        resolution=150.0,
        save_all=True,
        append_images=pages[1:],
    )
    return out
