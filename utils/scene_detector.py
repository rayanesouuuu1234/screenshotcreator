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
    hamming_distance,
    is_near_duplicate,
)
from utils.frame_quality import is_visually_empty_bgr

SCREENSHOT_DIR = Path("outputs/screenshots")
DEFAULT_MAX_SCREENSHOTS = 80

# Adaptive detection defaults (no UI tuning required)
STATIC_CHANGE_SCORE = 2.5
STATIC_STREAK_PAUSE = 6
DEBOUNCE_SAMPLES = 2
MIN_CHANGE_THRESHOLD = 5.0
MAX_CHANGE_THRESHOLD = 14.0
DEFAULT_CHANGE_THRESHOLD = 8.0

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


def _read_frame_at(cap: cv2.VideoCapture, t: float, crop: dict[str, float]) -> tuple[np.ndarray, np.ndarray] | None:
    cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
    ok, frame = cap.read()
    if not ok or frame is None:
        return None
    frame = apply_crop_margins_bgr(
        frame,
        crop_left_pct=crop["left"],
        crop_right_pct=crop["right"],
        crop_top_pct=crop["top"],
        crop_bottom_pct=crop["bottom"],
    )
    return frame, _prepare_frame(frame)


def _adaptive_sample_interval(duration: float) -> float:
    if duration <= 120:
        return 0.5
    if duration <= 600:
        return 0.75
    if duration <= 1800:
        return 1.0
    return min(2.5, duration / 900.0)


def _adaptive_min_gap(duration: float, shot_budget: int) -> float:
    if duration <= 0:
        return 2.0
    spread = duration / max(shot_budget, 1)
    return max(2.0, min(12.0, spread * 0.35))


def _probe_change_threshold(
    cap: cv2.VideoCapture,
    duration: float,
    crop: dict[str, float],
) -> float:
    """Sample early timeline to pick a change threshold for this recording."""
    probe_times = [0.0]
    step = min(45.0, max(15.0, duration / 8.0))
    t = step
    while t < min(duration, 180.0):
        probe_times.append(t)
        t += step

    scores: list[float] = []
    prev_prepared: np.ndarray | None = None
    for t in probe_times:
        sample = _read_frame_at(cap, t, crop)
        if sample is None:
            continue
        _frame, prepared = sample
        if prev_prepared is not None:
            scores.append(compute_scene_change_score(prepared, prev_prepared))
        prev_prepared = prepared

    if not scores:
        return DEFAULT_CHANGE_THRESHOLD

    peak = float(max(scores))
    if peak < 4.0:
        return MAX_CHANGE_THRESHOLD
    if peak > 22.0:
        return MIN_CHANGE_THRESHOLD
    return max(MIN_CHANGE_THRESHOLD, min(MAX_CHANGE_THRESHOLD, peak * 0.42))


def _is_single_screen_video(
    cap: cv2.VideoCapture,
    duration: float,
    crop: dict[str, float],
) -> bool:
    """True when coarse probes all look like the same UI (e.g. one frame for an hour)."""
    if duration < 30.0:
        return False

    step = min(120.0, max(30.0, duration / 10.0))
    times = [0.0]
    t = step
    while t <= duration:
        times.append(t)
        t += step

    hashes: list[int] = []
    for probe_t in times:
        sample = _read_frame_at(cap, probe_t, crop)
        if sample is None:
            continue
        _frame, prepared = sample
        if not is_visually_empty_bgr(_frame):
            hashes.append(dhash(prepared))

    if len(hashes) < 2:
        return len(hashes) == 1

    reference = hashes[0]
    return all(hamming_distance(reference, h) < 10 for h in hashes[1:])


def _save_screenshot(
    frame: np.ndarray,
    timestamp: float,
    change_percent: float,
) -> dict:
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SCREENSHOT_DIR / _format_filename(timestamp)
    cv2.imwrite(str(path), frame)
    return {
        "timestamp": float(timestamp),
        "label": format_timestamp(timestamp),
        "path": str(path),
        "change_percent": float(change_percent),
        "capture_reason": "change",
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


def _dedupe_screenshot_list(shots: list[dict]) -> list[dict]:
    if len(shots) <= 1:
        return shots

    kept: list[dict] = []
    last_hash: int | None = None
    for shot in sorted(shots, key=lambda s: float(s["timestamp"])):
        path = Path(str(shot.get("path", "")))
        if not path.is_file():
            kept.append(shot)
            continue
        frame = cv2.imread(str(path))
        if frame is None:
            kept.append(shot)
            continue
        frame_hash = dhash(_prepare_frame(frame))
        if is_near_duplicate(last_hash, frame_hash):
            continue
        kept.append(shot)
        last_hash = frame_hash
    return kept


def _detect_single_screen(
    cap: cv2.VideoCapture,
    duration: float,
    crop: dict[str, float],
    *,
    max_screenshots: int,
    on_progress: ProgressCb,
) -> list[dict]:
    if on_progress:
        on_progress("Detecting screen changes", 90)
    sample = _read_frame_at(cap, 0.0, crop)
    if sample is None:
        return []
    frame, prepared = sample
    screenshots: list[dict] = []
    _try_save_screenshot(
        screenshots,
        frame=frame,
        prepared=prepared,
        timestamp=0.0,
        change_percent=0.0,
        last_saved_hash=None,
        max_screenshots=max_screenshots,
    )
    return screenshots


def detect_scenes(
    video_path: str,
    *,
    change_threshold: float | None = None,
    min_gap: float | None = None,
    sample_interval: float | None = None,
    max_gap_sec: float = 0.0,
    max_screenshots: int = DEFAULT_MAX_SCREENSHOTS,
    crop_left_pct: float = 0.0,
    crop_right_pct: float = 0.0,
    crop_top_pct: float = 0.0,
    crop_bottom_pct: float = 0.0,
    include_first_frame: bool = True,
    on_progress: ProgressCb = None,
) -> list[dict]:
    """
    Save screenshots when the UI meaningfully changes.

    Adapts to the recording: single static screen → one capture; active walkthroughs
    → debounced change detection with duplicate suppression.
    """
    _ = max_gap_sec  # interval captures disabled; kept for API compatibility

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    clear_screenshots_dir()
    duration = _video_duration_sec(cap)
    duration = duration if duration > 0 else 1.0
    max_screenshots = max(1, int(max_screenshots))

    crop = {
        "left": float(crop_left_pct),
        "right": float(crop_right_pct),
        "top": float(crop_top_pct),
        "bottom": float(crop_bottom_pct),
    }

    if _is_single_screen_video(cap, duration, crop):
        shots = _detect_single_screen(
            cap,
            duration,
            crop,
            max_screenshots=max_screenshots,
            on_progress=on_progress,
        )
        cap.release()
        if on_progress:
            on_progress("Screenshots saved", 95)
        return shots

    threshold = (
        float(change_threshold)
        if change_threshold is not None
        else _probe_change_threshold(cap, duration, crop)
    )
    sample_interval = (
        float(sample_interval)
        if sample_interval is not None
        else _adaptive_sample_interval(duration)
    )
    sample_interval = max(0.25, sample_interval)
    min_gap = (
        float(min_gap)
        if min_gap is not None
        else _adaptive_min_gap(duration, max_screenshots)
    )
    min_gap = max(1.0, min_gap)

    screenshots: list[dict] = []
    last_saved_prepared: np.ndarray | None = None
    last_saved_hash: int | None = None
    last_saved_at = -float("inf")
    consecutive_above_threshold = 0
    pending_score = 0.0
    static_streak = 0
    t = 0.0

    while t <= duration + 0.001:
        if on_progress:
            on_progress("Detecting screen changes", int(min(90, (t / duration) * 90)))

        sample = _read_frame_at(cap, t, crop)
        if sample is None:
            break
        frame, prepared = sample

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

        if change_score < STATIC_CHANGE_SCORE:
            static_streak += 1
        else:
            static_streak = 0

        if static_streak >= STATIC_STREAK_PAUSE:
            consecutive_above_threshold = 0
            pending_score = 0.0
            t += sample_interval
            continue

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
                static_streak = 0
            consecutive_above_threshold = 0
            pending_score = 0.0

        t += sample_interval

    cap.release()
    screenshots = _dedupe_screenshot_list(screenshots)

    if on_progress:
        on_progress("Screenshots saved", 95)
    return sorted(screenshots, key=lambda shot: float(shot["timestamp"]))


def clear_screenshots_dir() -> None:
    if SCREENSHOT_DIR.exists():
        shutil.rmtree(SCREENSHOT_DIR)
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
