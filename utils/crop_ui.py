"""Streamlit crop UI — keeps margin % in session state for the pipeline."""

from __future__ import annotations

import base64
from pathlib import Path

import cv2
import numpy as np
import streamlit as st

from utils.crop import load_preview_frame_bgr
from utils.crop_selector import render_interactive_crop_selector

DEFAULT_CROP = {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}


def normalize_crop_pct(value: dict | None) -> dict[str, float]:
    crop = dict(DEFAULT_CROP)
    if not isinstance(value, dict):
        return crop
    for key in crop:
        try:
            crop[key] = max(0.0, min(50.0, float(value.get(key, 0.0) or 0.0)))
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


def _bump_crop_init_revision() -> None:
    st.session_state["crop_init_revision"] = int(st.session_state.get("crop_init_revision", 0)) + 1


def reset_crop_margins() -> None:
    set_crop_margins(dict(DEFAULT_CROP))
    _bump_crop_init_revision()


def _crop_init_token(cache_key: str) -> str:
    revision = int(st.session_state.get("crop_init_revision", 0))
    return f"{cache_key}::{revision}"


def _frame_to_jpeg_base64(frame: np.ndarray) -> str:
    ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 88])
    if not ok:
        raise ValueError("Could not encode preview frame.")
    return base64.b64encode(buffer.tobytes()).decode("ascii")


def render_video_crop_ui(cache_path: Path) -> dict[str, float]:
    """Bounded drag crop; returns margin % applied to all frames when generating."""
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

    height, width = frame.shape[:2]
    image_b64 = _frame_to_jpeg_base64(frame)
    display_max = 920
    component_height = max(1, int(height * min(1.0, display_max / max(width, 1)))) + 24

    header_col, reset_col = st.columns([5, 1])
    with header_col:
        st.caption(
            "Optional — drag the handles to trim edges, or leave unchanged and click Generate."
        )
    with reset_col:
        if st.button("Reset", help="Use the full frame", use_container_width=True):
            reset_crop_margins()
            st.rerun()

    updated = render_interactive_crop_selector(
        image_b64,
        width,
        height,
        get_crop_margins(),
        height=component_height,
        init_token=_crop_init_token(cache_key),
        key=f"video_crop_{cache_key}",
    )
    if updated:
        set_crop_margins(updated)

    return get_crop_margins()
