"""Streamlit-native crop UI — sliders + live preview (no custom component iframe)."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import streamlit as st

from utils.crop import load_preview_frame_bgr

DEFAULT_CROP = {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}
MAX_TRIM_PCT = 45.0

TRIM_LABELS = {
    "left": "Left edge",
    "right": "Right edge",
    "top": "Top edge",
    "bottom": "Bottom edge",
}


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
    cache_key = str(st.session_state.get("upload_cache_key", ""))
    for side in DEFAULT_CROP:
        for prefix in ("crop_sl_", "crop_num_", "crop_trim_"):
            key = f"{prefix}{side}_{cache_key}"
            st.session_state.pop(key, None)
        st.session_state[f"crop_margin_{side}"] = 0.0


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
    dimmed = (rgb.astype(np.float32) * 0.28).astype(np.uint8)
    preview = dimmed.copy()
    preview[top:bottom, left:right] = rgb[top:bottom, left:right]
    cv2.rectangle(preview, (left, top), (right - 1, bottom - 1), (56, 189, 248), 3)
    return preview


def _clamp_trim(value: float) -> float:
    return max(0.0, min(MAX_TRIM_PCT, float(value)))


def _render_trim_control(side: str, label: str, cache_key: str) -> float:
    """Label + typed % + slider; crop_margin_* is the source of truth."""
    state_key = f"crop_margin_{side}"
    slider_key = f"crop_sl_{side}_{cache_key}"
    number_key = f"crop_num_{side}_{cache_key}"

    margin = _clamp_trim(st.session_state.get(state_key, 0.0))
    st.session_state[state_key] = margin
    st.session_state[slider_key] = margin
    st.session_state[number_key] = margin

    def sync_from_slider() -> None:
        st.session_state[state_key] = _clamp_trim(st.session_state[slider_key])

    def sync_from_number() -> None:
        st.session_state[state_key] = _clamp_trim(st.session_state[number_key])

    title_col, value_col = st.columns([2, 1])
    with title_col:
        st.markdown(f"**{label}**")
        st.caption("Percent to cut from this edge")
    with value_col:
        st.number_input(
            "Percent",
            min_value=0.0,
            max_value=MAX_TRIM_PCT,
            step=0.5,
            format="%.1f",
            key=number_key,
            on_change=sync_from_number,
        )

    st.slider(
        label,
        min_value=0.0,
        max_value=MAX_TRIM_PCT,
        step=0.5,
        format="%.1f%%",
        key=slider_key,
        label_visibility="collapsed",
        on_change=sync_from_slider,
    )

    return float(st.session_state[state_key])


def _render_margin_controls(cache_key: str) -> dict[str, float]:
    updated: dict[str, float] = {}

    row_top = st.columns(2, gap="large")
    for col, side in zip(row_top, ("top", "bottom")):
        with col:
            updated[side] = _render_trim_control(side, TRIM_LABELS[side], cache_key)

    row_sides = st.columns(2, gap="large")
    for col, side in zip(row_sides, ("left", "right")):
        with col:
            updated[side] = _render_trim_control(side, TRIM_LABELS[side], cache_key)

    set_crop_margins(updated)
    return get_crop_margins()


def _render_crop_body(frame: np.ndarray, cache_key: str) -> dict[str, float]:
    reset_col, _ = st.columns([1, 3])
    with reset_col:
        if st.button("Reset crop", help="Use the full frame", use_container_width=True):
            reset_crop_margins()
            st.rerun()

    margins = get_crop_margins()
    preview_rgb = draw_crop_preview(frame, margins)
    st.image(preview_rgb, use_container_width=True, channels="RGB")

    frame_h, frame_w = frame.shape[:2]
    left, top, right, bottom = _crop_pixels(frame_h, frame_w, margins)
    crop_w = right - left
    crop_h = bottom - top
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Width kept", f"{crop_w} px")
    m2.metric("Height kept", f"{crop_h} px")
    m3.metric("Width", f"{100 * crop_w / frame_w:.0f}%")
    m4.metric("Height", f"{100 * crop_h / frame_h:.0f}%")

    st.divider()
    return _render_margin_controls(cache_key)


def render_video_crop_ui(cache_path: Path, *, bordered: bool = True) -> dict[str, float]:
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

    if bordered:
        with st.container(border=True):
            st.markdown("### Trim frame edges (optional)")
            st.caption(
                "Bright area is kept. Adjust top/bottom and left/right — "
                "use the slider or type a percent."
            )
            margins = _render_crop_body(frame, cache_key)
    else:
        margins = _render_crop_body(frame, cache_key)

    return margins
