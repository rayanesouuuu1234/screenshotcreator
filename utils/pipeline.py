"""End-to-end video screenshot extraction pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from utils.exporter import create_screenshots_docx
from utils.frame_quality import is_visually_empty_image
from utils.scene_detector import detect_scenes
from utils.transcriber import transcribe_video

ProgressCb = Callable[[str, int], None] | None
CONSULTANT_PROMPT_PATH = Path("consultant_ai_prompt.md")

DEFAULT_MIN_GAP = 3.0
DEFAULT_SAMPLE_INTERVAL = 1.0
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


def _load_ai_instructions() -> str:
    if CONSULTANT_PROMPT_PATH.is_file():
        return CONSULTANT_PROMPT_PATH.read_text(encoding="utf-8")
    return ""


def run_screenshot_pipeline(
    video_path: str,
    *,
    filename: str,
    change_threshold: float,
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

    progress("Detecting meaningful screen changes", 1)
    screenshots = detect_scenes(
        video_path,
        change_threshold=change_threshold,
        min_gap=DEFAULT_MIN_GAP,
        sample_interval=DEFAULT_SAMPLE_INTERVAL,
        crop_left_pct=crop_left_pct,
        crop_right_pct=crop_right_pct,
        crop_top_pct=crop_top_pct,
        crop_bottom_pct=crop_bottom_pct,
        on_progress=lambda message, pct: progress(message, int(pct * 0.55)),
    )

    screenshots, skipped_empty_frames = _filter_visually_empty_screenshots(screenshots)
    print(f"Skipped {skipped_empty_frames} visually empty frame(s) before document assembly.")

    progress("Transcribing with faster-whisper", 58)
    transcript = transcribe_video(
        video_path,
        model_size=DEFAULT_WHISPER_MODEL,
        output_path=None,
        on_progress=lambda message, pct: progress(message, 58 + int(pct * 0.34)),
    )

    progress("Generating Word document", 94)
    docx_path = create_screenshots_docx(
        screenshots,
        video_filename=filename,
        transcript_segments=transcript.get("segments") or [],
        ai_instructions=_load_ai_instructions(),
    )

    result: dict[str, Any] = {
        "filename": filename,
        "settings": {
            "change_threshold": float(change_threshold),
            "min_gap": DEFAULT_MIN_GAP,
            "sample_interval": DEFAULT_SAMPLE_INTERVAL,
            "crop_left_pct": float(crop_left_pct),
            "crop_right_pct": float(crop_right_pct),
            "crop_top_pct": float(crop_top_pct),
            "crop_bottom_pct": float(crop_bottom_pct),
            "whisper_model_size": DEFAULT_WHISPER_MODEL,
        },
        "screenshots": screenshots,
        "skipped_empty_frames": skipped_empty_frames,
        "docx_path": str(docx_path),
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
