"""Detect meaningful screen changes in a video and save screenshots."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from utils.crop import apply_crop_margins_bgr

SCREENSHOT_DIR = Path("outputs/screenshots")

ProgressCb = Callable[[str, int], None] | None


def format_timestamp(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _format_filename(seconds: float) -> str:
    return format_timestamp(seconds).replace(":", "_") + ".png"


def _video_duration_sec(cap: cv2.VideoCapture) -> float:
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if fps > 0 and frame_count > 0:
        return float(frame_count) / float(fps)
    cap.set(cv2.CAP_PROP_POS_MSEC, 1e9)
    cap.read()
    pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0
    return float(pos_ms) / 1000.0 if pos_ms > 0 else 0.0


def _prepare_frame(frame: np.ndarray, width: int = 320) -> np.ndarray:
    h, w = frame.shape[:2]
    if w > width:
        ratio = width / float(w)
        frame = cv2.resize(frame, (width, max(1, int(h * ratio))), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.GaussianBlur(gray, (5, 5), 0)


def _changed_area_percent(current: np.ndarray, previous: np.ndarray) -> float:
    diff = cv2.absdiff(current, previous)
    _, mask = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    changed = cv2.countNonZero(mask)
    total = mask.shape[0] * mask.shape[1]
    return (changed / max(total, 1)) * 100.0


def _save_screenshot(frame: np.ndarray, timestamp: float, change_percent: float) -> dict:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / _format_filename(timestamp)
    cv2.imwrite(str(path), frame)
    return {
        "timestamp": float(timestamp),
        "label": format_timestamp(timestamp),
        "path": str(path),
        "change_percent": float(change_percent),
    }


def detect_scenes(
    video_path: str,
    *,
    change_threshold: float = 10.0,
    min_gap: float = 3.0,
    sample_interval: float = 1.0,
    crop_left_pct: float = 0.0,
    crop_right_pct: float = 0.0,
    crop_top_pct: float = 0.0,
    crop_bottom_pct: float = 0.0,
    include_first_frame: bool = True,
    on_progress: ProgressCb = None,
) -> list[dict]:
    """
    Save screenshots for substantial visual changes.

    The algorithm compares blurred grayscale samples and measures what percentage
    of pixels changed beyond a fixed per-pixel delta. This rejects small encoding
    noise while still catching new screens, modal states, and large content updates.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    clear_screenshots_dir()
    duration = _video_duration_sec(cap)
    duration = duration if duration > 0 else 1.0
    sample_interval = max(0.1, float(sample_interval))
    min_gap = max(0.0, float(min_gap))

    screenshots: list[dict] = []
    previous_prepared: np.ndarray | None = None
    last_saved_at = -float("inf")
    t = 0.0

    while t <= duration + 0.001:
        if on_progress:
            on_progress("Detecting screen changes", int(min(90, (t / duration) * 90)))

        cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
        ok, frame = cap.read()
        if not ok or frame is None:
            break

        frame = apply_crop_margins_bgr(
            frame,
            crop_left_pct=crop_left_pct,
            crop_right_pct=crop_right_pct,
            crop_top_pct=crop_top_pct,
            crop_bottom_pct=crop_bottom_pct,
        )
        prepared = _prepare_frame(frame)
        if previous_prepared is None:
            if include_first_frame:
                screenshots.append(_save_screenshot(frame, 0.0, 100.0))
                last_saved_at = 0.0
            previous_prepared = prepared
            t += sample_interval
            continue

        change_percent = _changed_area_percent(prepared, previous_prepared)
        enough_change = change_percent >= float(change_threshold)
        enough_gap = (t - last_saved_at) >= min_gap
        if enough_change and enough_gap:
            screenshots.append(_save_screenshot(frame, t, change_percent))
            last_saved_at = t

        previous_prepared = prepared
        t += sample_interval

    cap.release()

    if on_progress:
        on_progress("Screenshots saved", 95)
    return sorted(screenshots, key=lambda shot: float(shot["timestamp"]))


def clear_screenshots_dir() -> None:
    if SCREENSHOT_DIR.exists():
        shutil.rmtree(SCREENSHOT_DIR)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
