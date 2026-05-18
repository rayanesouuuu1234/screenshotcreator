"""End-to-end video screenshot extraction pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from utils.exporter import create_screenshots_pdf
from utils.scene_detector import detect_scenes
from utils.transcriber import transcribe_video

ProgressCb = Callable[[str, int], None] | None


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

    progress("Generating PDF", 58)
    pdf_path = create_screenshots_pdf(screenshots, video_filename=filename)

    progress("Transcribing with faster-whisper", 64)
    transcript = transcribe_video(
        video_path,
        model_size=whisper_model_size,
        output_path=Path("outputs") / "transcript.txt",
        on_progress=lambda message, pct: progress(message, 64 + int(pct * 0.34)),
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
