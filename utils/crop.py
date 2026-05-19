"""Crop margin helpers shared by the UI and scene detector."""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

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


def margins_from_box(box: dict[str, Any] | tuple | list, image_width: int, image_height: int) -> dict[str, float]:
    """Convert pixel crop box to margin percentages."""
    if isinstance(box, (tuple, list)) and len(box) >= 4:
        left = float(box[0])
        top = float(box[1])
        width = float(box[2])
        height = float(box[3])
    elif isinstance(box, dict):
        left = float(box.get("left", 0))
        top = float(box.get("top", 0))
        width = float(box.get("width", image_width))
        height = float(box.get("height", image_height))
    else:
        return {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}

    image_width = max(1, int(image_width))
    image_height = max(1, int(image_height))
    width = max(1.0, min(width, float(image_width)))
    height = max(1.0, min(height, float(image_height)))
    left = max(0.0, min(left, float(image_width - 1)))
    top = max(0.0, min(top, float(image_height - 1)))

    return {
        "left": round(100.0 * left / image_width, 1),
        "right": round(100.0 * (image_width - left - width) / image_width, 1),
        "top": round(100.0 * top / image_height, 1),
        "bottom": round(100.0 * (image_height - top - height) / image_height, 1),
    }


def load_preview_frame_bgr(video_path: str | Path) -> np.ndarray | None:
    """Load the same preview frame used for cropping (skips leading black frames)."""
    encoded = extract_preview_frame_base64(video_path)
    if not encoded:
        return None
    image_b64, _width, _height = encoded
    buffer = np.frombuffer(base64.b64decode(image_b64), dtype=np.uint8)
    frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    return frame
