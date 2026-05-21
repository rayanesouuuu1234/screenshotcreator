"""PDF export: packed screenshots + full transcript appendix."""

from __future__ import annotations

import re
import textwrap
from datetime import date
from pathlib import Path

from PIL import Image
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

OUTPUT_DIR = Path("outputs")

PAGE_W, PAGE_H = letter
MARGIN = 0.28 * inch
CONTENT_W = PAGE_W - 2 * MARGIN
CONTENT_H = PAGE_H - 2 * MARGIN

TIMESTAMP_PT = 7.5
TIMESTAMP_LEAD = 10
SHOT_GAP = 0.06 * inch
MIN_SLOT_H = 1.35 * inch
MAX_IMAGE_H = 3.5 * inch

APPENDIX_HEADING_PT = 11
APPENDIX_HEADING_LEAD = 16

TRANSCRIPT_PT = 6.5
TRANSCRIPT_LEAD = 7.5
TRANSCRIPT_CHARS_PER_LINE = 118


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem or "video"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return stem or "video"


def default_pdf_name(video_filename: str) -> str:
    return f"{_safe_stem(video_filename)}_{date.today().isoformat()}.pdf"


def _parse_timestamp_seconds(value: str | float | int) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    text = str(value).strip()
    if not text:
        return 0.0
    parts = text.split(":")
    if len(parts) == 3:
        h, m, s = (int(float(p)) for p in parts)
        return float(h * 3600 + m * 60 + s)
    if len(parts) == 2:
        m, s = (int(float(p)) for p in parts)
        return float(m * 60 + s)
    try:
        return max(0.0, float(text))
    except ValueError:
        return 0.0


def _shot_timestamp_seconds(shot: dict) -> float:
    if "timestamp" in shot:
        return _parse_timestamp_seconds(shot["timestamp"])
    return _parse_timestamp_seconds(shot.get("label", "00:00:00"))


def _image_aspect(image_path: Path) -> float:
    with Image.open(image_path) as img:
        width_px, height_px = img.size
    if width_px <= 0 or height_px <= 0:
        return 9 / 16
    return height_px / width_px


def _capped_natural_image_height(image_path: Path) -> float:
    return min(CONTENT_W * _image_aspect(image_path), MAX_IMAGE_H)


def _shot_block_height(image_path: Path) -> float:
    return TIMESTAMP_LEAD + _capped_natural_image_height(image_path)


def _prepare_shots(screenshots: list[dict]) -> list[dict]:
    valid = [
        shot
        for shot in screenshots
        if Path(str(shot.get("path", ""))).is_file()
    ]
    return sorted(valid, key=_shot_timestamp_seconds)


def _layout_page_heights(page_shots: list[dict]) -> list[float]:
    image_heights = [
        _capped_natural_image_height(Path(str(shot.get("path", ""))))
        for shot in page_shots
    ]
    if not image_heights:
        return []

    n = len(image_heights)
    gaps = SHOT_GAP * max(0, n - 1)
    labels = TIMESTAMP_LEAD * n
    image_budget = CONTENT_H - gaps - labels
    total_image = sum(image_heights)
    scale = min(1.0, image_budget / total_image) if total_image > 0 else 1.0
    return [h * scale for h in image_heights]


def _pack_screenshot_pages(shots: list[dict]) -> list[list[dict]]:
    pages: list[list[dict]] = []
    current: list[dict] = []
    used = 0.0

    for shot in shots:
        image_path = Path(str(shot.get("path", "")))
        block_h = max(_shot_block_height(image_path), MIN_SLOT_H)
        gap = SHOT_GAP if current else 0.0
        needed = used + gap + block_h

        if current and needed > CONTENT_H:
            pages.append(current)
            current = [shot]
            used = block_h
        else:
            used = needed
            current.append(shot)

    if current:
        pages.append(current)
    return pages


def _draw_screenshot_page(c: canvas.Canvas, page_shots: list[dict]) -> None:
    if not page_shots:
        return

    image_heights = _layout_page_heights(page_shots)
    y = PAGE_H - MARGIN

    for index, (shot, image_h) in enumerate(zip(page_shots, image_heights, strict=False)):
        image_path = Path(str(shot.get("path", "")))

        if index > 0:
            y -= SHOT_GAP

        label = str(shot.get("label", "00:00:00"))
        c.setFont("Helvetica-Bold", TIMESTAMP_PT)
        c.setFillColorRGB(0.2, 0.2, 0.2)
        c.drawString(MARGIN, y - TIMESTAMP_LEAD + 2, label)
        y -= TIMESTAMP_LEAD

        c.drawImage(
            ImageReader(str(image_path)),
            MARGIN,
            y - image_h,
            width=CONTENT_W,
            height=image_h,
            preserveAspectRatio=True,
            anchor="nw",
            mask="auto",
        )
        y -= image_h


def _wrap_transcript_lines(transcript_text: str) -> list[str]:
    lines: list[str] = []
    for raw in transcript_text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        lines.extend(textwrap.wrap(stripped, width=TRANSCRIPT_CHARS_PER_LINE) or [stripped])
    return lines


def _draw_transcript_pages(c: canvas.Canvas, transcript_text: str) -> None:
    lines = _wrap_transcript_lines(transcript_text)
    if not lines:
        return

    y = PAGE_H - MARGIN
    c.setFont("Helvetica-Bold", APPENDIX_HEADING_PT)
    c.setFillColorRGB(0.15, 0.15, 0.15)
    c.drawString(MARGIN, y - APPENDIX_HEADING_LEAD + 2, "Full Transcript")
    y -= APPENDIX_HEADING_LEAD

    c.setFont("Helvetica", TRANSCRIPT_PT)
    c.setFillColorRGB(0.12, 0.12, 0.12)
    line_h = TRANSCRIPT_LEAD
    bottom = MARGIN

    for line in lines:
        if y - line_h < bottom:
            c.showPage()
            c.setFont("Helvetica", TRANSCRIPT_PT)
            c.setFillColorRGB(0.12, 0.12, 0.12)
            y = PAGE_H - MARGIN

        c.drawString(MARGIN, y - line_h, line)
        y -= line_h


def create_screenshots_pdf(
    screenshots: list[dict],
    *,
    video_filename: str,
    output_path: str | Path | None = None,
    transcript_text: str = "",
    segments: list[dict] | None = None,
) -> Path:
    """Create a PDF with packed screenshots (timestamp + image only) and full transcript."""
    _ = segments  # per-shot captions intentionally not rendered

    if not screenshots:
        raise ValueError("No screenshots were generated, so a document cannot be created.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(output_path) if output_path else OUTPUT_DIR / default_pdf_name(video_filename)

    shots = _prepare_shots(screenshots)
    pages = _pack_screenshot_pages(shots)
    if not pages:
        raise ValueError("None of the generated screenshot files could be read.")

    c = canvas.Canvas(str(out), pagesize=letter)

    has_transcript = bool(transcript_text.strip())
    for index, page_shots in enumerate(pages):
        _draw_screenshot_page(c, page_shots)
        if index < len(pages) - 1 or has_transcript:
            c.showPage()

    if has_transcript:
        _draw_transcript_pages(c, transcript_text)

    c.save()
    return out
