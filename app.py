"""Streamlit UI: walkthrough video → timestamped screenshots + transcript document."""

from __future__ import annotations

import html
import importlib
import json
import os
import shutil
from pathlib import Path

import streamlit as st

from utils.crop_ui import get_crop_margins, reset_crop_margins

import utils.exporter as exporter_module
import utils.pipeline as pipeline_module
import utils.scene_detector as scene_detector_module

exporter_module = importlib.reload(exporter_module)
scene_detector_module = importlib.reload(scene_detector_module)
pipeline_module = importlib.reload(pipeline_module)
run_screenshot_pipeline = pipeline_module.run_screenshot_pipeline

APP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = APP_DIR / "outputs"
UPLOAD_CACHE_DIR = APP_DIR / ".upload_cache"
LAST_RESULT_PATH = OUTPUT_DIR / "last_result.json"
MAX_UPLOAD_BYTES = 2000 * 1024 * 1024

os.chdir(APP_DIR)

st.set_page_config(
    page_title="Screenshot Document",
    page_icon="logo.jpeg",
    layout="wide",
)

APP_CSS = """
<style>
  #MainMenu, footer, header { visibility: hidden; }
  .stApp {
    background: linear-gradient(180deg, #0b1020 0%, #07080c 48%, #050609 100%);
    color: #f8fafc;
  }
  .block-container { max-width: 920px; padding-top: 1.5rem; padding-bottom: 3rem; }
  h1 { font-size: 2rem; letter-spacing: -0.04em; margin-bottom: 0.25rem; }
  h2, h3 { letter-spacing: -0.03em; }
  [data-testid="stFileUploader"] section {
    border: 1px dashed rgba(96, 165, 250, 0.45);
    border-radius: 16px;
    padding: 1rem;
  }
  [data-testid="stSlider"] label p,
  [data-testid="stSlider"] [data-testid="stMarkdownContainer"] p {
    font-size: 1.2rem !important;
    font-weight: 600 !important;
    color: #f1f5f9 !important;
    line-height: 1.35 !important;
  }
  [data-testid="stSlider"] [data-testid="stThumbValue"],
  [data-testid="stSlider"] [data-testid="stTickBarMin"],
  [data-testid="stSlider"] [data-testid="stTickBarMax"] {
    font-size: 1.05rem !important;
    font-weight: 600 !important;
  }
  div[data-baseweb="slider"] { padding-top: 0.6rem; padding-bottom: 1.2rem; }
  div[data-baseweb="slider"] > div { height: 10px !important; }
  div[data-baseweb="slider"] [role="slider"] {
    width: 22px !important;
    height: 22px !important;
  }
  [data-testid="stNumberInput"] label p {
    font-size: 0.95rem !important;
    font-weight: 600 !important;
    color: #cbd5e1 !important;
  }
  [data-testid="stNumberInput"] input {
    font-size: 1.1rem !important;
    font-weight: 700 !important;
    text-align: center;
    min-height: 2.6rem;
    background-color: #1e293b !important;
    color: #f8fafc !important;
    border: 1px solid #64748b !important;
    border-radius: 10px !important;
  }
  [data-testid="stNumberInput"] button {
    background-color: #334155 !important;
    color: #f8fafc !important;
    border-color: #64748b !important;
  }
  /* Primary Generate — force dark blue (Streamlit theme overrides otherwise) */
  .stButton > button[kind="primary"],
  .stButton > button[data-testid="stBaseButton-primary"],
  button[data-testid="stBaseButton-primary"],
  [data-testid="stButton"] button[kind="primary"] {
    min-height: 3.1rem;
    font-size: 1.1rem;
    font-weight: 700;
    border-radius: 14px;
    background: linear-gradient(135deg, #1e40af 0%, #1e3a8a 100%) !important;
    background-color: #1e3a8a !important;
    color: #ffffff !important;
    border: 1px solid #3b82f6 !important;
    box-shadow: 0 4px 14px rgba(30, 64, 175, 0.45);
  }
  .stButton > button[kind="primary"]:hover,
  button[data-testid="stBaseButton-primary"]:hover {
    background: linear-gradient(135deg, #2563eb 0%, #1e40af 100%) !important;
    background-color: #1e40af !important;
    color: #ffffff !important;
    border-color: #60a5fa !important;
  }
  .stButton > button[kind="primary"]:disabled,
  button[data-testid="stBaseButton-primary"]:disabled {
    background: #334155 !important;
    background-color: #334155 !important;
    color: #94a3b8 !important;
    border-color: #475569 !important;
    box-shadow: none;
  }
  .stButton > button[kind="secondary"],
  .stButton > button:not([kind="primary"]) {
    background-color: #1e293b !important;
    color: #e2e8f0 !important;
    border: 1px solid #475569 !important;
    border-radius: 12px;
  }
  .stDownloadButton > button {
    min-height: 3.1rem;
    font-size: 1.1rem;
    font-weight: 700;
    border-radius: 14px;
    background: linear-gradient(135deg, #0f766e 0%, #115e59 100%) !important;
    background-color: #0f766e !important;
    color: #ffffff !important;
    border: 1px solid #14b8a6 !important;
  }
  [data-testid="stMetricLabel"] {
    font-size: 0.85rem !important;
    color: #94a3b8 !important;
  }
  [data-testid="stMetricValue"] {
    font-size: 1.35rem !important;
    font-weight: 700 !important;
    color: #f1f5f9 !important;
  }
  [data-testid="stCaptionContainer"] p {
    color: #94a3b8 !important;
    font-size: 0.95rem !important;
  }
  div[data-testid="stVerticalBlockBorderWrapper"] {
    border-color: rgba(96, 165, 250, 0.35) !important;
    background: rgba(15, 23, 42, 0.55) !important;
    border-radius: 16px !important;
    padding: 0.25rem 0.5rem 0.75rem !important;
  }
  hr { margin: 1.25rem 0; opacity: 0.25; }
</style>
"""


def _path_exists(path_value: str) -> bool:
    return bool(path_value) and Path(path_value).is_file()


def get_result_doc_path(result: dict) -> Path | None:
    for key in ("docx_path", "pdf_path"):
        path = Path(str(result.get(key) or ""))
        if path.is_file():
            return path
    return None


def is_restorable_result(result: dict) -> bool:
    if not isinstance(result, dict):
        return False
    if get_result_doc_path(result) is None:
        return False
    screenshots = result.get("screenshots") or []
    return any(_path_exists(str(shot.get("path") or "")) for shot in screenshots)


def load_last_result() -> dict | None:
    if not LAST_RESULT_PATH.is_file():
        return None
    try:
        result = json.loads(LAST_RESULT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return result if is_restorable_result(result) else None


def restore_last_result() -> None:
    if st.session_state.get("last_result"):
        return
    result = load_last_result()
    if result:
        st.session_state["last_result"] = result


def save_last_result(result: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LAST_RESULT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")


def clear_current_result() -> None:
    st.session_state.pop("last_result", None)
    st.session_state.pop("upload_cache_key", None)
    st.session_state.pop("crop_preview_key", None)
    st.session_state.pop("crop_preview_bgr", None)
    st.session_state.pop("crop_pct", None)
    st.session_state.pop("crop_margins_for_pipeline", None)
    for side in ("left", "right", "top", "bottom"):
        st.session_state.pop(f"crop_margin_{side}", None)
    clear_outputs()
    if UPLOAD_CACHE_DIR.exists():
        shutil.rmtree(UPLOAD_CACHE_DIR)


def clear_outputs() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    (OUTPUT_DIR / "screenshots").mkdir(parents=True, exist_ok=True)


def ensure_upload_cached(uploaded_file) -> Path | None:
    if uploaded_file is None:
        return None
    UPLOAD_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(uploaded_file.name).suffix or ".mp4"
    cache_path = UPLOAD_CACHE_DIR / f"current_upload{suffix}"
    cache_key = f"{uploaded_file.name}:{uploaded_file.size}"
    cache_changed = st.session_state.get("upload_cache_key") != cache_key
    if cache_changed or not cache_path.is_file():
        cache_path.write_bytes(uploaded_file.getbuffer())
        st.session_state["upload_cache_key"] = cache_key
        if cache_changed:
            reset_crop_margins()
    return cache_path


def run_app() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)
    restore_last_result()

    st.title("Recording Analyzer")

    uploaded = st.file_uploader(
        "Video",
        type=["mp4", "mov", "m4v", "avi", "mkv", "webm"],
        label_visibility="collapsed",
    )

    over_size = uploaded is not None and uploaded.size > MAX_UPLOAD_BYTES
    if over_size:
        st.error("Max file size is 200 MB.")

    cache_path = None
    if uploaded is not None and not over_size:
        cache_path = ensure_upload_cached(uploaded)
        st.session_state["crop_margins_for_pipeline"] = get_crop_margins()

    run = st.button(
        "Generate",
        type="primary",
        use_container_width=True,
        disabled=uploaded is None or over_size,
    )

    if run and uploaded is not None:
        cache_path = ensure_upload_cached(uploaded)
        if cache_path is None or not cache_path.is_file():
            st.error("Could not read the uploaded video.")
            return

        crop_margins = get_crop_margins()
        st.session_state["crop_margins_for_pipeline"] = crop_margins
        clear_outputs()

        progress = st.progress(0)
        progress_text = st.empty()

        def on_progress(message: str, percent: int) -> None:
            progress.progress(max(0, min(100, percent)))
            progress_text.markdown(f"{html.escape(message)} · {percent}%")

        try:
            with st.status("Processing…", expanded=False) as status:
                result = run_screenshot_pipeline(
                    str(cache_path),
                    filename=uploaded.name,
                    crop_left_pct=crop_margins["left"],
                    crop_right_pct=crop_margins["right"],
                    crop_top_pct=crop_margins["top"],
                    crop_bottom_pct=crop_margins["bottom"],
                    on_progress=on_progress,
                )
                status.update(label="Done", state="complete")
            st.session_state["last_result"] = result
            save_last_result(result)
            progress.empty()
            progress_text.empty()
        except Exception as exc:
            st.error(f"Failed: {exc}")

    result = st.session_state.get("last_result")
    pdf_path = get_result_doc_path(result) if result else None

    if pdf_path and pdf_path.is_file():
        st.download_button(
            "Download PDF",
            data=pdf_path.read_bytes(),
            file_name=pdf_path.name,
            mime="application/pdf",
            use_container_width=True,
        )

    if result and st.button("Clear", use_container_width=True):
        clear_current_result()
        st.rerun()


if __name__ == "__main__":
    run_app()
