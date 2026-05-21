"""Crop margin helpers shared by the UI and scene detector."""

from __future__ import annotations

import base64
from pathlib import Path

import cv2
import numpy as np

from utils.frame_quality import extract_preview_frame_base64


def apply_crop_margins_bgr(
    frame: np.ndarray,
    *,
    crop_left_pct: float = 0.0,
    crop_right_pct: float = 0.0,
    crop_top_pct: float = 0.0,
    crop_bottom_pct: float = 0.0,
) -> np.ndarray:
    """Trim frame edges using margin percentages (same semantics as scene_detector)."""
    height, width = frame.shape[:2]
    left = int(width * max(0.0, min(float(crop_left_pct), 80.0)) / 100.0)
    right = width - int(width * max(0.0, min(float(crop_right_pct), 80.0)) / 100.0)
    top = int(height * max(0.0, min(float(crop_top_pct), 80.0)) / 100.0)
    bottom = height - int(height * max(0.0, min(float(crop_bottom_pct), 80.0)) / 100.0)
    if right - left < 10 or bottom - top < 10:
        return frame
    return frame[top:bottom, left:right]


def load_preview_frame_bgr(video_path: str | Path) -> np.ndarray | None:
    """Load the same preview frame used for cropping (skips leading black frames)."""
    encoded = extract_preview_frame_base64(video_path)
    if not encoded:
        return None
    image_b64, _width, _height = encoded
    buffer = np.frombuffer(base64.b64decode(image_b64), dtype=np.uint8)
    frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    return frame
