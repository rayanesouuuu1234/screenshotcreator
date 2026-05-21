"""End-to-end video screenshot extraction pipeline."""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any, Callable

from utils.frame_quality import is_visually_empty_image
from utils.scene_detector import detect_scenes
from utils.transcriber import transcribe_video

ProgressCb = Callable[[str, int], None] | None

DEFAULT_MAX_SCREENSHOTS = 80
DEFAULT_WHISPER_MODEL = "base"


def _filter_visually_empty_screenshots(screenshots: list[dict]) -> tuple[list[dict], int]:
    kept: list[dict] = []
    skipped = 0
    for screenshot in screenshots:
        image_path = Path(str(screenshot.get("path", "")))
        if not image_path.is_file():
            kept.append(screenshot)
            continue
        if is_visually_empty_image(image_path):
            skipped += 1
            continue
        kept.append(screenshot)
    return kept, skipped


def run_screenshot_pipeline(
    video_path: str,
    *,
    filename: str,
    crop_left_pct: float = 0.0,
    crop_right_pct: float = 0.0,
    crop_top_pct: float = 0.0,
    crop_bottom_pct: float = 0.0,
    on_progress: ProgressCb = None,
) -> dict[str, Any]:
    """Detect meaningful video changes, transcribe audio, and generate outputs."""

    def progress(message: str, percent: int) -> None:
        if on_progress:
            on_progress(message, percent)

    progress("Detecting screen changes", 1)
    screenshots = detect_scenes(
        video_path,
        max_screenshots=DEFAULT_MAX_SCREENSHOTS,
        crop_left_pct=crop_left_pct,
        crop_right_pct=crop_right_pct,
        crop_top_pct=crop_top_pct,
        crop_bottom_pct=crop_bottom_pct,
        on_progress=lambda message, pct: progress(message, int(pct * 0.55)),
    )

    screenshots, skipped_empty_frames = _filter_visually_empty_screenshots(screenshots)

    progress("Transcribing", 58)
    transcript = transcribe_video(
        video_path,
        model_size=DEFAULT_WHISPER_MODEL,
        output_path=None,
        on_progress=lambda message, pct: progress(message, 58 + int(pct * 0.34)),
    )

    transcript_text = str(transcript.get("text") or "")

    progress("Building document", 94)
    from utils import exporter as exporter_module

    importlib.reload(exporter_module)
    pdf_path = exporter_module.create_screenshots_pdf(
        screenshots,
        video_filename=filename,
        transcript_text=transcript_text,
    )

    result: dict[str, Any] = {
        "filename": filename,
        "settings": {
            "detection": "adaptive",
            "max_screenshots": DEFAULT_MAX_SCREENSHOTS,
            "crop_left_pct": float(crop_left_pct),
            "crop_right_pct": float(crop_right_pct),
            "crop_top_pct": float(crop_top_pct),
            "crop_bottom_pct": float(crop_bottom_pct),
            "whisper_model_size": DEFAULT_WHISPER_MODEL,
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
