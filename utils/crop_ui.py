"""Streamlit crop UI — keeps margin % in session state for the pipeline."""

from __future__ import annotations

from pathlib import Path

import cv2
import streamlit as st
from PIL import Image

from utils.crop import apply_crop_margins_bgr, load_preview_frame_bgr, margins_from_box

DEFAULT_CROP = {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}

CROP_UI_CSS = """
<style>
  .crop-workspace {
    margin: 0.5rem 0 1.25rem;
    padding: 1.35rem 1.4rem 1.5rem;
    border-radius: 22px;
    border: 1px solid rgba(96, 165, 250, 0.22);
    background:
      linear-gradient(145deg, rgba(15, 23, 42, 0.94), rgba(17, 24, 39, 0.82)),
      radial-gradient(circle at 0% 0%, rgba(96, 165, 250, 0.12), transparent 42%);
    box-shadow: 0 24px 60px rgba(0, 0, 0, 0.35);
  }
  .crop-intro {
    margin: 0;
    color: #cbd5e1;
    font-size: 0.98rem;
    line-height: 1.55;
  }
  .crop-intro strong { color: #f8fafc; font-weight: 700; }
  .crop-panel-label {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    margin: 0 0 0.35rem;
    color: #f1f5f9;
    font-size: 0.92rem;
    font-weight: 800;
    letter-spacing: -0.02em;
  }
  .crop-panel-label .dot {
    width: 0.55rem;
    height: 0.55rem;
    border-radius: 999px;
    background: linear-gradient(135deg, #38bdf8, #8b5cf6);
    box-shadow: 0 0 12px rgba(56, 189, 248, 0.65);
  }
  .crop-panel-hint {
    margin: 0 0 0.65rem;
    color: #94a3b8;
    font-size: 0.84rem;
    line-height: 1.45;
  }
  .crop-preview-badge {
    display: inline-block;
    margin-bottom: 0.55rem;
    padding: 0.28rem 0.65rem;
    border-radius: 999px;
    background: rgba(34, 197, 94, 0.16);
    border: 1px solid rgba(74, 222, 128, 0.35);
    color: #bbf7d0;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.02em;
    text-transform: uppercase;
  }
  .crop-preview-shell {
    padding: 0.55rem;
    border-radius: 14px;
    background: rgba(15, 23, 42, 0.9);
    border: 1px solid rgba(96, 165, 250, 0.28);
    box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.8) inset, 0 18px 42px rgba(37, 99, 235, 0.12);
  }
  .crop-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 0.45rem;
    margin: 0.75rem 0 0.15rem;
  }
  .crop-chip {
    padding: 0.32rem 0.72rem;
    border-radius: 999px;
    border: 1px solid rgba(96, 165, 250, 0.28);
    background: rgba(37, 99, 235, 0.14);
    color: #dbeafe;
    font-size: 0.8rem;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }
  .crop-chip span { color: #93c5fd; font-weight: 500; }
  div[data-testid="stExpander"]:has(.crop-finetune-marker) {
    border-color: rgba(148, 163, 184, 0.14);
    background: rgba(15, 23, 42, 0.45);
    border-radius: 16px;
  }
  div[data-testid="stHorizontalBlock"]:has(iframe[title="st_cropper.st_cropper"]) {
    justify-content: center;
  }
  iframe[title="st_cropper.st_cropper"] {
    border-radius: 12px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, 0.35);
  }
</style>
"""


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


def reset_crop_margins() -> None:
    set_crop_margins(dict(DEFAULT_CROP))


def _ensure_margin_widget_defaults() -> None:
    for side in DEFAULT_CROP:
        key = f"crop_margin_{side}"
        if key not in st.session_state:
            st.session_state[key] = float(
                st.session_state.get("crop_pct", DEFAULT_CROP).get(side, 0.0)
            )


def _panel_heading(title: str, hint: str) -> None:
    st.markdown(
        f"""
        <p class="crop-panel-label"><span class="dot"></span> {title}</p>
        <p class="crop-panel-hint">{hint}</p>
        """,
        unsafe_allow_html=True,
    )


def _render_margin_chips(margins: dict[str, float]) -> None:
    chips = []
    for side, label in [("left", "Left"), ("right", "Right"), ("top", "Top"), ("bottom", "Bottom")]:
        value = margins.get(side, 0.0)
        chips.append(f'<span class="crop-chip"><span>{label}</span> {value:.1f}%</span>')
    st.markdown(f'<div class="crop-chips">{"".join(chips)}</div>', unsafe_allow_html=True)


def _render_cropper(pil_image: Image.Image, frame_width: int, frame_height: int) -> dict[str, float] | None:
    try:
        from streamlit_cropper import st_cropper
    except ImportError:
        return None

    box = st_cropper(
        pil_image,
        realtime_update=True,
        return_type="box",
        aspect_ratio=None,
        box_color="#38bdf8",
        stroke_width=3,
        key="video_crop_box",
    )
    if not box:
        return None
    return margins_from_box(box, frame_width, frame_height)


def render_video_crop_ui(cache_path: Path) -> dict[str, float]:
    """Crop UI; returns margin % applied to all frames when generating."""
    st.markdown(CROP_UI_CSS, unsafe_allow_html=True)

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
    pil_image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
    rgb_full = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    st.markdown(
        """
        <div class="crop-workspace">
          <p class="crop-intro">
            <strong>Optional:</strong> Remove meeting side panels or browser chrome.
            Drag the blue box on your video frame — the preview on the right updates as you crop.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    margins = get_crop_margins()
    cropped = apply_crop_margins_bgr(
        frame,
        crop_left_pct=margins["left"],
        crop_right_pct=margins["right"],
        crop_top_pct=margins["top"],
        crop_bottom_pct=margins["bottom"],
    )
    rgb_cropped = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)

    col_edit, col_preview = st.columns([1.15, 0.85], gap="large")

    with col_edit:
        header_col, reset_col = st.columns([4, 1])
        with header_col:
            _panel_heading("Adjust crop", "Drag corners or edges on the frame below.")
        with reset_col:
            st.markdown("<div style='height:1.5rem'></div>", unsafe_allow_html=True)
            if st.button("Reset", help="Use the full frame", use_container_width=True):
                reset_crop_margins()
                st.rerun()

        margins_from_cropper = _render_cropper(pil_image, width, height)
        if margins_from_cropper is not None:
            set_crop_margins(margins_from_cropper)
            margins = get_crop_margins()
            cropped = apply_crop_margins_bgr(
                frame,
                crop_left_pct=margins["left"],
                crop_right_pct=margins["right"],
                crop_top_pct=margins["top"],
                crop_bottom_pct=margins["bottom"],
            )
            rgb_cropped = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
        else:
            st.image(rgb_full, use_container_width=True)
            st.caption("Install `streamlit-cropper` for drag-to-crop.")

    with col_preview:
        _panel_heading("Screenshot preview", "All generated screenshots will match this.")
        st.markdown('<span class="crop-preview-badge">Live preview</span>', unsafe_allow_html=True)
        st.markdown('<div class="crop-preview-shell">', unsafe_allow_html=True)
        st.image(rgb_cropped, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with st.expander("Fine-tune edges (optional)", expanded=False):
        st.markdown('<span class="crop-finetune-marker"></span>', unsafe_allow_html=True)
        st.caption("Adjust individual edges if you need precise control.")
        _ensure_margin_widget_defaults()
        cols = st.columns(4)
        labels = {"left": "Left", "right": "Right", "top": "Top", "bottom": "Bottom"}
        for side, col in zip(("left", "right", "top", "bottom"), cols):
            with col:
                st.slider(labels[side], 0.0, 50.0, step=0.5, key=f"crop_margin_{side}")

    margins = get_crop_margins()
    _render_margin_chips(margins)
    return margins
