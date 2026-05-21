"""PDF export: packed screenshots + per-shot transcript captions + full appendix."""

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

CAPTION_PT = 7.0
CAPTION_LEAD = 8.5
CAPTION_PAD_V = 5
CAPTION_PAD_H = 8
CAPTION_GAP = 0.08 * inch
CAPTION_CHARS_PER_LINE = 102
CAPTION_BORDER_W = 2.0

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


def _normalize_segments(segments: list[dict] | None) -> list[dict]:
    normalized: list[dict] = []
    for raw in segments or []:
        if not isinstance(raw, dict):
            continue
        text = str(raw.get("text", "")).strip()
        if not text:
            continue
        start = float(raw.get("start", 0.0))
        end = float(raw.get("end", start))
        normalized.append({"start": start, "end": end, "text": text})
    return sorted(normalized, key=lambda seg: seg["start"])


def _shot_timestamp_seconds(shot: dict) -> float:
    if "timestamp" in shot:
        return _parse_timestamp_seconds(shot["timestamp"])
    return _parse_timestamp_seconds(shot.get("label", "00:00:00"))


def _segments_for_shot_window(
    segments: list[dict],
    window_start: float,
    window_end: float | None,
) -> list[dict]:
    """Segments whose start time falls in [window_start, window_end)."""
    matched: list[dict] = []
    for seg in segments:
        start = float(seg["start"])
        if start < window_start:
            continue
        if window_end is not None and start >= window_end:
            continue
        matched.append(seg)
    return matched


def _caption_text_from_segments(matched: list[dict]) -> str:
    if not matched:
        return ""
    parts = [str(seg["text"]).strip() for seg in matched if str(seg.get("text", "")).strip()]
    return " ".join(parts)


def _wrap_caption_lines(text: str) -> list[str]:
    if not text.strip():
        return []
    inner_w = CAPTION_CHARS_PER_LINE
    lines: list[str] = []
    for paragraph in text.split("\n"):
        stripped = paragraph.strip()
        if not stripped:
            continue
        lines.extend(textwrap.wrap(stripped, width=inner_w) or [stripped])
    return lines


def _estimate_caption_height(text: str) -> float:
    lines = _wrap_caption_lines(text)
    if not lines:
        return 0.0
    body = len(lines) * CAPTION_LEAD
    return float(CAPTION_PAD_V * 2) + body


def _image_aspect(image_path: Path) -> float:
    with Image.open(image_path) as img:
        width_px, height_px = img.size
    if width_px <= 0 or height_px <= 0:
        return 9 / 16
    return height_px / width_px


def _capped_natural_image_height(image_path: Path) -> float:
    return min(CONTENT_W * _image_aspect(image_path), MAX_IMAGE_H)


def _shot_block_height(image_path: Path, caption_height: float) -> float:
    block = TIMESTAMP_LEAD + _capped_natural_image_height(image_path)
    if caption_height > 0:
        block += CAPTION_GAP + caption_height
    return block


def _enrich_shots(screenshots: list[dict], segments: list[dict]) -> list[dict]:
    valid = [
        shot
        for shot in screenshots
        if Path(str(shot.get("path", ""))).is_file()
    ]
    valid.sort(key=_shot_timestamp_seconds)

    times = [_shot_timestamp_seconds(shot) for shot in valid]
    enriched: list[dict] = []

    for index, shot in enumerate(valid):
        window_start = times[index]
        window_end = times[index + 1] if index + 1 < len(times) else None
        matched = _segments_for_shot_window(segments, window_start, window_end)
        caption = _caption_text_from_segments(matched)
        item = dict(shot)
        item["_caption_text"] = caption
        item["_caption_height"] = _estimate_caption_height(caption)
        enriched.append(item)

    return enriched


def _layout_page_heights(page_shots: list[dict]) -> list[float]:
    """Reserve caption space; scale image heights to fit page without exceeding MAX_IMAGE_H."""
    image_heights: list[float] = []
    caption_heights: list[float] = []

    for shot in page_shots:
        image_path = Path(str(shot.get("path", "")))
        image_heights.append(_capped_natural_image_height(image_path))
        caption_heights.append(float(shot.get("_caption_height", 0.0)))

    if not image_heights:
        return []

    n = len(image_heights)
    gaps = SHOT_GAP * max(0, n - 1)
    labels = TIMESTAMP_LEAD * n
    caption_block = sum(caption_heights) + CAPTION_GAP * sum(1 for h in caption_heights if h > 0)
    image_budget = CONTENT_H - gaps - labels - caption_block
    total_image = sum(image_heights)
    scale = min(1.0, image_budget / total_image) if total_image > 0 else 1.0
    return [h * scale for h in image_heights]


def _pack_screenshot_pages(enriched_shots: list[dict]) -> list[list[dict]]:
    pages: list[list[dict]] = []
    current: list[dict] = []
    used = 0.0

    for shot in enriched_shots:
        image_path = Path(str(shot.get("path", "")))
        caption_h = float(shot.get("_caption_height", 0.0))
        block_h = max(_shot_block_height(image_path, caption_h), MIN_SLOT_H)
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


def _draw_caption_block(c: canvas.Canvas, x: float, top_y: float, width: float, text: str) -> float:
    """Draw caption below image; return block height used (points)."""
    lines = _wrap_caption_lines(text)
    if not lines:
        return 0.0

    block_h = _estimate_caption_height(text)
    bottom_y = top_y - block_h

    c.setFillColorRGB(0.95, 0.97, 0.99)
    c.rect(x, bottom_y, width, block_h, stroke=0, fill=1)

    border_x = x
    c.setFillColorRGB(0.23, 0.51, 0.96)
    c.rect(border_x, bottom_y, CAPTION_BORDER_W, block_h, stroke=0, fill=1)

    text_x = x + CAPTION_PAD_H + CAPTION_BORDER_W
    text_y = top_y - CAPTION_PAD_V
    c.setFont("Helvetica", CAPTION_PT)
    c.setFillColorRGB(0.15, 0.17, 0.21)

    for line in lines:
        text_y -= CAPTION_LEAD
        c.drawString(text_x, text_y, line)

    return block_h


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

        caption = str(shot.get("_caption_text", ""))
        if caption.strip():
            y -= CAPTION_GAP
            y -= _draw_caption_block(c, MARGIN, y, CONTENT_W, caption)


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
    """Create a PDF with packed screenshots, per-shot captions, and a full transcript appendix."""
    if not screenshots:
        raise ValueError("No screenshots were generated, so a document cannot be created.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(output_path) if output_path else OUTPUT_DIR / default_pdf_name(video_filename)

    norm_segments = _normalize_segments(segments)
    enriched = _enrich_shots(screenshots, norm_segments)
    pages = _pack_screenshot_pages(enriched)
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
