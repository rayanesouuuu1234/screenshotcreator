"""Detect blank/black frames and pick a usable preview frame for cropping."""

from __future__ import annotations

import base64
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageStat

MIN_FRAME_BRIGHTNESS = 15.0
MIN_FRAME_VARIANCE = 100.0
DEFAULT_PREVIEW_SCAN_SECONDS = 45.0


def frame_stats_bgr(frame: np.ndarray) -> tuple[float, float]:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return float(gray.mean()), float(gray.var())


def is_black_frame_bgr(frame: np.ndarray) -> bool:
    """True for leading black frames (brightness-only; solid UI colors are kept)."""
    mean_brightness, _pixel_variance = frame_stats_bgr(frame)
    return mean_brightness < MIN_FRAME_BRIGHTNESS


def is_visually_empty_bgr(frame: np.ndarray) -> bool:
    mean_brightness, pixel_variance = frame_stats_bgr(frame)
    return mean_brightness < MIN_FRAME_BRIGHTNESS or pixel_variance < MIN_FRAME_VARIANCE


def is_visually_empty_image(image_path: str | Path) -> bool:
    with Image.open(image_path) as image:
        grayscale = image.convert("L")
        stats = ImageStat.Stat(grayscale)
    mean_brightness = float(stats.mean[0])
    pixel_variance = float(stats.var[0])
    return mean_brightness < MIN_FRAME_BRIGHTNESS or pixel_variance < MIN_FRAME_VARIANCE


def _encode_frame_jpeg_base64(frame: np.ndarray) -> tuple[str, int, int] | None:
    height, width = frame.shape[:2]
    ok_enc, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok_enc:
        return None
    encoded = base64.b64encode(buffer.tobytes()).decode("ascii")
    return encoded, width, height


def extract_preview_frame_base64(
    video_path: str | Path,
    *,
    max_scan_seconds: float = DEFAULT_PREVIEW_SCAN_SECONDS,
) -> tuple[str, int, int] | None:
    """Return a JPEG base64 preview, skipping leading black/blank frames when possible."""
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        cap.release()
        return None

    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    if fps <= 0:
        fps = 30.0
    max_frames = max(1, int(max_scan_seconds * fps))

    first_frame: np.ndarray | None = None
    best_frame: np.ndarray | None = None
    best_score = -1.0
    frames_read = 0

    while frames_read < max_frames:
        ok, frame = cap.read()
        if not ok or frame is None:
            break
        frames_read += 1
        if first_frame is None:
            first_frame = frame

        if not is_black_frame_bgr(frame):
            cap.release()
            return _encode_frame_jpeg_base64(frame)

        mean_brightness, pixel_variance = frame_stats_bgr(frame)
        score = mean_brightness * pixel_variance
        if score > best_score:
            best_score = score
            best_frame = frame

    cap.release()
    fallback = best_frame if best_frame is not None else first_frame
    if fallback is None:
        return None
    return _encode_frame_jpeg_base64(fallback)
