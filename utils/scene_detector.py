"""Detect meaningful screen changes in a video and save screenshots."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from utils.crop import apply_crop_margins_bgr
from utils.frame_compare import (
    compute_scene_change_score,
    dhash,
    is_near_duplicate,
)
from utils.frame_quality import is_visually_empty_bgr

SCREENSHOT_DIR = Path("outputs/screenshots")
DEFAULT_MAX_SCREENSHOTS = 80
DEBOUNCE_SAMPLES = 2

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


def _try_save_screenshot(
    screenshots: list[dict],
    *,
    frame: np.ndarray,
    prepared: np.ndarray,
    timestamp: float,
    change_percent: float,
    last_saved_hash: int | None,
    max_screenshots: int,
) -> tuple[bool, int | None]:
    if len(screenshots) >= max_screenshots:
        return False, last_saved_hash
    if is_visually_empty_bgr(frame):
        return False, last_saved_hash

    frame_hash = dhash(prepared)
    if is_near_duplicate(last_saved_hash, frame_hash):
        return False, last_saved_hash

    screenshots.append(_save_screenshot(frame, timestamp, change_percent))
    return True, frame_hash


def detect_scenes(
    video_path: str,
    *,
    change_threshold: float = 10.0,
    min_gap: float = 3.0,
    sample_interval: float = 0.5,
    max_screenshots: int = DEFAULT_MAX_SCREENSHOTS,
    crop_left_pct: float = 0.0,
    crop_right_pct: float = 0.0,
    crop_top_pct: float = 0.0,
    crop_bottom_pct: float = 0.0,
    include_first_frame: bool = True,
    on_progress: ProgressCb = None,
) -> list[dict]:
    """
    Save screenshots for substantial visual changes.

    Uses background-masked pixel diff + edge structure vs the last saved frame,
    with debouncing, in-loop empty-frame skipping, and perceptual-hash dedup.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    clear_screenshots_dir()
    duration = _video_duration_sec(cap)
    duration = duration if duration > 0 else 1.0
    sample_interval = max(0.1, float(sample_interval))
    min_gap = max(0.0, float(min_gap))
    max_screenshots = max(1, int(max_screenshots))
    threshold = float(change_threshold)

    screenshots: list[dict] = []
    last_saved_prepared: np.ndarray | None = None
    last_saved_hash: int | None = None
    last_saved_at = -float("inf")
    consecutive_above_threshold = 0
    pending_score = 0.0
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

        if last_saved_prepared is None:
            if include_first_frame and not is_visually_empty_bgr(frame):
                saved, last_saved_hash = _try_save_screenshot(
                    screenshots,
                    frame=frame,
                    prepared=prepared,
                    timestamp=0.0,
                    change_percent=100.0,
                    last_saved_hash=last_saved_hash,
                    max_screenshots=max_screenshots,
                )
                if saved:
                    last_saved_at = 0.0
            last_saved_prepared = prepared.copy()
            if last_saved_hash is None:
                last_saved_hash = dhash(prepared)
            t += sample_interval
            continue

        change_score = compute_scene_change_score(prepared, last_saved_prepared)
        enough_gap = (t - last_saved_at) >= min_gap

        if change_score >= threshold:
            consecutive_above_threshold += 1
            pending_score = max(pending_score, change_score)
        else:
            consecutive_above_threshold = 0
            pending_score = 0.0

        if consecutive_above_threshold >= DEBOUNCE_SAMPLES and enough_gap:
            saved, last_saved_hash = _try_save_screenshot(
                screenshots,
                frame=frame,
                prepared=prepared,
                timestamp=t,
                change_percent=pending_score,
                last_saved_hash=last_saved_hash,
                max_screenshots=max_screenshots,
            )
            if saved:
                last_saved_prepared = prepared.copy()
                last_saved_at = t
            consecutive_above_threshold = 0
            pending_score = 0.0

        t += sample_interval

    cap.release()

    if on_progress:
        on_progress("Screenshots saved", 95)
    return sorted(screenshots, key=lambda shot: float(shot["timestamp"]))


def clear_screenshots_dir() -> None:
    if SCREENSHOT_DIR.exists():
        shutil.rmtree(SCREENSHOT_DIR)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
