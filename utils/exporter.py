"""PDF export for chronological screenshots."""

from __future__ import annotations

import re
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


def _safe_stem(filename: str) -> str:
    stem = Path(filename).stem or "video"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._")
    return stem or "video"


def _font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ):
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


def create_screenshots_pdf(
    screenshots: list[dict],
    *,
    video_filename: str,
    output_path: str | Path | None = None,
) -> Path:
    """Create a full-width sequential PDF with timestamp-labeled screenshots."""
    if not screenshots:
        raise ValueError("No screenshots were generated, so a PDF cannot be created.")

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(output_path) if output_path else PDF_DIR / f"{_safe_stem(video_filename)}_screenshots.pdf"

    pages: list[Image.Image] = []
    label_font = _font(22)

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
        page_height = image_y + image_height + BOTTOM_PADDING
        page = Image.new("RGB", (PAGE_WIDTH, page_height), "white")
        draw = ImageDraw.Draw(page)
        label = str(shot.get("label", "00:00:00"))
        draw.text((24, TOP_PADDING), f"{index}. {label}", fill="#111111", font=label_font)
        page.paste(resized, (0, image_y))
        draw.line(
            [(0, page_height - BOTTOM_PADDING // 2), (PAGE_WIDTH, page_height - BOTTOM_PADDING // 2)],
            fill="#DDDDDD",
            width=DIVIDER_WIDTH,
        )
        pages.append(page)

    if not pages:
        raise ValueError("None of the generated screenshot files could be read.")

    pages[0].save(
        out,
        format="PDF",
        resolution=150.0,
        save_all=True,
        append_images=pages[1:],
    )
    return out
