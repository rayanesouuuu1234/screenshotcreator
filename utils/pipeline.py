"""End-to-end video screenshot extraction pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from PIL import Image, ImageStat

from utils.exporter import create_screenshots_pdf
from utils.scene_detector import detect_scenes
from utils.transcriber import transcribe_video

ProgressCb = Callable[[str, int], None] | None
MIN_FRAME_BRIGHTNESS = 15.0
MIN_FRAME_VARIANCE = 100.0


def _is_visually_empty_frame(image_path: str | Path) -> bool:
    with Image.open(image_path) as image:
        grayscale = image.convert("L")
        stats = ImageStat.Stat(grayscale)
    mean_brightness = float(stats.mean[0])
    pixel_variance = float(stats.var[0])
    return mean_brightness < MIN_FRAME_BRIGHTNESS or pixel_variance < MIN_FRAME_VARIANCE


def _filter_visually_empty_screenshots(screenshots: list[dict]) -> tuple[list[dict], int]:
    kept: list[dict] = []
    skipped = 0
    for screenshot in screenshots:
        image_path = Path(str(screenshot.get("path", "")))
        if not image_path.is_file():
            kept.append(screenshot)
            continue
        if _is_visually_empty_frame(image_path):
            skipped += 1
            continue
        kept.append(screenshot)
    return kept, skipped


def run_screenshot_pipeline(
    video_path: str,
    *,
    filename: str,
    change_threshold: float,
    min_gap: float,
    sample_interval: float,
    whisper_model_size: str = "base",
    on_progress: ProgressCb = None,
) -> dict[str, Any]:
    """Detect meaningful video changes, transcribe audio, and generate outputs."""

    def progress(message: str, percent: int) -> None:
        if on_progress:
            on_progress(message, percent)

    progress("Detecting meaningful screen changes", 1)
    screenshots = detect_scenes(
        video_path,
        change_threshold=change_threshold,
        min_gap=min_gap,
        sample_interval=sample_interval,
        on_progress=lambda message, pct: progress(message, int(pct * 0.55)),
    )

    screenshots, skipped_empty_frames = _filter_visually_empty_screenshots(screenshots)
    print(f"Skipped {skipped_empty_frames} visually empty frame(s) before PDF assembly.")

    progress("Transcribing with faster-whisper", 58)
    transcript = transcribe_video(
        video_path,
        model_size=whisper_model_size,
        output_path=None,
        on_progress=lambda message, pct: progress(message, 58 + int(pct * 0.34)),
    )

    progress("Generating PDF", 94)
    pdf_path = create_screenshots_pdf(
        screenshots,
        video_filename=filename,
        transcript_segments=transcript.get("segments") or [],
    )

    result: dict[str, Any] = {
        "filename": filename,
        "settings": {
            "change_threshold": float(change_threshold),
            "min_gap": float(min_gap),
            "sample_interval": float(sample_interval),
            "whisper_model_size": whisper_model_size,
        },
        "screenshots": screenshots,
        "skipped_empty_frames": skipped_empty_frames,
        "pdf_path": str(pdf_path),
        "transcript": transcript,
    }

    out_root = Path("outputs")
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "screenshots.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )

    progress("Complete", 100)
    return result
