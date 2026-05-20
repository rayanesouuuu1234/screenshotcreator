"""Streamlit-native crop UI — sliders + live preview (no custom component iframe)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import streamlit as st

from utils.crop import load_preview_frame_bgr

DEFAULT_CROP = {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}
MAX_TRIM_PCT = 45.0
PREVIEW_MAX_WIDTH = 920


def normalize_crop_pct(value: dict | None) -> dict[str, float]:
    crop = dict(DEFAULT_CROP)
    if not isinstance(value, dict):
        return crop
    for key in crop:
        try:
            crop[key] = max(0.0, min(MAX_TRIM_PCT, float(value.get(key, 0.0) or 0.0)))
        except (TypeError, ValueError):
            crop[key] = 0.0
    return crop


def set_crop_margins(crop: dict[str, float]) -> None:
    normalized = normalize_crop_pct(crop)
    st.session_state["crop_pct"] = normalized
    for side, value in normalized.items():
        st.session_state[f"crop_margin_{side}"] = value


def get_crop_margins() -> dict[str, float]:
    return normalize_crop_pct(
        {
            "left": st.session_state.get("crop_margin_left", 0.0),
            "right": st.session_state.get("crop_margin_right", 0.0),
            "top": st.session_state.get("crop_margin_top", 0.0),
            "bottom": st.session_state.get("crop_margin_bottom", 0.0),
        }
    )


def reset_crop_margins() -> None:
    set_crop_margins(dict(DEFAULT_CROP))


def _crop_pixels(
    frame_h: int,
    frame_w: int,
    margins: dict[str, float],
) -> tuple[int, int, int, int]:
    left = int(frame_w * margins["left"] / 100.0)
    right = frame_w - int(frame_w * margins["right"] / 100.0)
    top = int(frame_h * margins["top"] / 100.0)
    bottom = frame_h - int(frame_h * margins["bottom"] / 100.0)
    right = max(left + 10, right)
    bottom = max(top + 10, bottom)
    return left, top, right, bottom


def draw_crop_preview(frame_bgr: np.ndarray, margins: dict[str, float]) -> np.ndarray:
    """RGB preview: dimmed outside crop, bright inside, cyan border."""
    frame_h, frame_w = frame_bgr.shape[:2]
    left, top, right, bottom = _crop_pixels(frame_h, frame_w, margins)

    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    dimmed = (rgb.astype(np.float32) * 0.32).astype(np.uint8)
    preview = dimmed.copy()
    preview[top:bottom, left:right] = rgb[top:bottom, left:right]
    cv2.rectangle(preview, (left, top), (right - 1, bottom - 1), (56, 189, 248), 2)
    return preview


def _render_margin_sliders(cache_key: str) -> dict[str, float]:
    margins = get_crop_margins()
    sides = (
        ("left", "Trim left"),
        ("right", "Trim right"),
        ("top", "Trim top"),
        ("bottom", "Trim bottom"),
    )

    row1, row2 = st.columns(2), st.columns(2)
    updated = dict(margins)

    for col, (side, label) in zip((row1[0], row1[1], row2[0], row2[1]), sides):
        with col:
            value = st.slider(
                label,
                min_value=0.0,
                max_value=MAX_TRIM_PCT,
                value=float(margins.get(side, 0.0)),
                step=0.5,
                format="%.1f%%",
                key=f"crop_trim_{side}_{cache_key}",
            )
            updated[side] = value

    set_crop_margins(updated)
    return get_crop_margins()


def render_video_crop_ui(cache_path: Path) -> dict[str, float]:
    """Crop via margin sliders and a live preview; same % semantics as the pipeline."""
    cache_key = st.session_state.get("upload_cache_key", "")
    preview_key = f"crop_preview::{cache_key}"

    if st.session_state.get("crop_preview_key") != preview_key:
        frame = load_preview_frame_bgr(cache_path)
        if frame is None:
            reset_crop_margins()
            return get_crop_margins()
        st.session_state["crop_preview_key"] = preview_key
        st.session_state["crop_preview_bgr"] = frame
        reset_crop_margins()

    frame = st.session_state.get("crop_preview_bgr")
    if frame is None:
        reset_crop_margins()
        return get_crop_margins()

    header_col, reset_col = st.columns([5, 1])
    with header_col:
        st.caption("Optional crop — adjust trim sliders; bright area is kept.")
    with reset_col:
        if st.button("Reset", help="Use the full frame", use_container_width=True):
            reset_crop_margins()
            st.rerun()

    margins = _render_margin_sliders(cache_key)
    preview_rgb = draw_crop_preview(frame, margins)
    st.image(preview_rgb, use_container_width=True, channels="RGB")

    frame_h, frame_w = frame.shape[:2]
    left, top, right, bottom = _crop_pixels(frame_h, frame_w, margins)
    crop_w = right - left
    crop_h = bottom - top
    st.caption(f"Export region: {crop_w}×{crop_h} px ({100 * crop_w / frame_w:.0f}% × {100 * crop_h / frame_h:.0f}% of frame)")

    return margins
