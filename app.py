"""Streamlit UI: walkthrough video → timestamped screenshots + transcript document."""

from __future__ import annotations

import html
import importlib
import json
import os
import shutil
from pathlib import Path

import streamlit as st

from utils.crop_ui import get_crop_margins, render_video_crop_ui, reset_crop_margins

import utils.pipeline as pipeline_module

pipeline_module = importlib.reload(pipeline_module)
run_screenshot_pipeline = pipeline_module.run_screenshot_pipeline
DEFAULT_CHANGE_THRESHOLD = pipeline_module.DEFAULT_CHANGE_THRESHOLD
DEFAULT_MIN_GAP = pipeline_module.DEFAULT_MIN_GAP
DEFAULT_SAMPLE_INTERVAL = pipeline_module.DEFAULT_SAMPLE_INTERVAL
DEFAULT_MAX_GAP_SEC = pipeline_module.DEFAULT_MAX_GAP_SEC

APP_DIR = Path(__file__).resolve().parent
LOGO_PATH = APP_DIR / "logo.jpeg"
OUTPUT_DIR = APP_DIR / "outputs"
UPLOAD_CACHE_DIR = APP_DIR / ".upload_cache"
LAST_RESULT_PATH = OUTPUT_DIR / "last_result.json"
MAX_UPLOAD_BYTES = 2000 * 1024 * 1024
MAX_UPLOAD_LABEL_MB = 200

os.chdir(APP_DIR)

st.set_page_config(
    page_title="Recording Analyzer",
    page_icon=str(LOGO_PATH) if LOGO_PATH.is_file() else None,
    layout="wide",
)

APP_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700&display=swap');

  #MainMenu, footer, header { visibility: hidden; }
  .stApp {
    font-family: "DM Sans", system-ui, -apple-system, sans-serif;
    background:
      radial-gradient(ellipse 80% 50% at 50% -20%, rgba(61, 171, 184, 0.12) 0%, transparent 55%),
      linear-gradient(180deg, #0a1628 0%, #070b14 45%, #050609 100%);
    color: #f8fafc;
  }
  .block-container {
    max-width: 980px;
    padding-top: 1.5rem;
    padding-bottom: 3.5rem;
  }

  [data-testid="stCaptionContainer"] p,
  .stCaption,
  [data-testid="stMarkdownContainer"] p.caption-like {
    letter-spacing: 0.01em;
    color: #94a3b8 !important;
  }

  [data-testid="stFileUploader"] section {
    border: 1px dashed rgba(96, 165, 250, 0.4) !important;
    border-radius: 12px;
    padding: 1rem;
    background: rgba(15, 23, 42, 0.45);
  }

  [data-testid="stSlider"] label p,
  [data-testid="stSlider"] [data-testid="stMarkdownContainer"] p {
    font-size: 1rem !important;
    font-weight: 500 !important;
    color: #e2e8f0 !important;
  }
  div[data-baseweb="slider"] > div {
    background: rgba(71, 85, 105, 0.5) !important;
  }
  div[data-baseweb="slider"] [role="slider"] {
    background: #3b82f6 !important;
  }

  [data-testid="stNumberInput"] input {
    background-color: #0f172a !important;
    color: #f8fafc !important;
    border: 1px solid #334155 !important;
    border-radius: 8px !important;
  }
  [data-testid="stNumberInput"] button {
    background-color: #1e293b !important;
    border-color: #334155 !important;
    color: #e2e8f0 !important;
  }

  [data-testid="stExpander"] details {
    border: 1px solid rgba(71, 85, 105, 0.45);
    border-radius: 12px;
    background: rgba(15, 23, 42, 0.4);
  }
  [data-testid="stExpander"] summary {
    border-top: 1px solid rgba(71, 85, 105, 0.35);
    font-weight: 600;
    color: #e2e8f0;
  }
  [data-testid="stExpander"] summary:first-of-type {
    border-top: none;
  }

  .stButton > button[kind="primary"],
  button[data-testid="stBaseButton-primary"] {
    min-height: 3rem;
    font-size: 1.05rem;
    font-weight: 600;
    border-radius: 12px;
    background: #1e40af !important;
    background-color: #1e40af !important;
    color: #ffffff !important;
    border: 1px solid #3b82f6 !important;
    box-shadow: none !important;
  }
  .stButton > button[kind="primary"]:hover {
    background: #2563eb !important;
    background-color: #2563eb !important;
    border-color: #60a5fa !important;
  }
  .stButton > button[kind="primary"]:disabled {
    background: #1e293b !important;
    background-color: #1e293b !important;
    color: #64748b !important;
    border-color: #334155 !important;
  }

  .stButton > button[kind="secondary"],
  .stButton > button:not([kind="primary"]) {
    min-height: 2.25rem;
    font-size: 0.9rem;
    background-color: transparent !important;
    color: #94a3b8 !important;
    border: 1px solid #475569 !important;
    border-radius: 10px;
  }

  .stDownloadButton > button {
    min-height: 3rem;
    font-size: 1.05rem;
    font-weight: 600;
    border-radius: 12px;
    background: linear-gradient(135deg, #0f766e 0%, #115e59 100%) !important;
    background-color: #0f766e !important;
    color: #ffffff !important;
    border: 1px solid #14b8a6 !important;
    box-shadow: none !important;
  }
  .stDownloadButton > button:hover {
    background: #0d9488 !important;
    background-color: #0d9488 !important;
    border-color: #2dd4bf !important;
  }

  .progress-status {
    font-size: 0.95rem;
    font-weight: 500;
    color: #94a3b8;
    letter-spacing: 0.01em;
  }

  [data-testid="stMetricLabel"] {
    font-size: 0.8rem !important;
    color: #94a3b8 !important;
    letter-spacing: 0.01em;
  }
  [data-testid="stMetricValue"] {
    font-size: 1.25rem !important;
    font-weight: 600 !important;
    color: #f1f5f9 !important;
  }

  hr {
    margin: 1.25rem 0 1.75rem 0;
    border: none;
    border-top: 1px solid rgba(71, 85, 105, 0.45);
  }
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


def render_header() -> None:
    logo_col, copy_col = st.columns([1, 4], vertical_alignment="center")
    with logo_col:
        if LOGO_PATH.is_file():
            st.image(str(LOGO_PATH), width=120)
    with copy_col:
        st.title("Recording Analyzer")
        st.markdown(
            "Upload a screen recording to generate a timestamped PDF with "
            "screenshots and transcript."
        )
    st.markdown("<hr>", unsafe_allow_html=True)


def render_detection_settings() -> tuple[float, float, float]:
    with st.expander("⚙️ Detection settings", expanded=False):
        change_threshold = st.slider(
            "Sensitivity",
            min_value=1.0,
            max_value=40.0,
            value=DEFAULT_CHANGE_THRESHOLD,
            step=0.5,
        )
        st.caption(
            "Higher values capture fewer screenshots. Lower values capture more."
        )
        min_gap = st.slider(
            "Minimum seconds between screenshots",
            min_value=1.0,
            max_value=15.0,
            value=DEFAULT_MIN_GAP,
            step=0.5,
        )
        st.caption("Prevents duplicate screenshots taken too close together.")
        sample_interval = st.slider(
            "Check every (seconds)",
            min_value=0.25,
            max_value=2.0,
            value=DEFAULT_SAMPLE_INTERVAL,
            step=0.25,
        )
        st.caption(
            "How often the video is sampled for changes. Lower is more thorough but slower."
        )
    return change_threshold, min_gap, sample_interval


def _format_duration(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def _video_duration_from_result(result: dict) -> str:
    screenshots = result.get("screenshots") or []
    timestamps: list[float] = []
    for shot in screenshots:
        try:
            timestamps.append(float(shot.get("timestamp", 0.0)))
        except (TypeError, ValueError):
            continue
    if not timestamps:
        return "—"
    return _format_duration(max(timestamps))


def _transcript_segment_count(result: dict) -> int:
    transcript = result.get("transcript")
    if not isinstance(transcript, dict):
        return 0
    segments = transcript.get("segments")
    if not isinstance(segments, list):
        return 0
    return len(segments)


def run_app() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)
    restore_last_result()

    render_header()

    st.markdown("**Upload your screen recording**")
    st.caption(
        f"MP4, MOV, MKV, WebM, AVI — max {MAX_UPLOAD_LABEL_MB} MB"
    )
    uploaded = st.file_uploader(
        "Upload your screen recording",
        type=["mp4", "mov", "m4v", "avi", "mkv", "webm"],
        label_visibility="collapsed",
    )

    over_size = uploaded is not None and uploaded.size > MAX_UPLOAD_BYTES
    if over_size:
        st.error(f"File exceeds the maximum upload size ({MAX_UPLOAD_LABEL_MB} MB).")

    has_upload = uploaded is not None and not over_size

    change_threshold, min_gap, sample_interval = render_detection_settings()

    crop_margins = {"left": 0.0, "right": 0.0, "top": 0.0, "bottom": 0.0}
    if has_upload:
        cache_path = ensure_upload_cached(uploaded)
        if cache_path is not None:
            with st.expander("✂️ Trim frame edges (optional)", expanded=False):
                st.caption(
                    "Use this to remove browser chrome, taskbars, or camera feeds "
                    "from the edges of your recording."
                )
                crop_margins = render_video_crop_ui(cache_path, bordered=False)
            st.session_state["crop_margins_for_pipeline"] = crop_margins

    run = st.button(
        "Generate PDF",
        type="primary",
        use_container_width=True,
        disabled=not has_upload,
    )

    if has_upload:
        st.caption("Estimated time: ~1 min per 10 minutes of video")
    else:
        st.caption("Upload a recording above to continue")

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
            progress_text.markdown(
                f'<p class="progress-status">{html.escape(message)} · {percent}%</p>',
                unsafe_allow_html=True,
            )

        try:
            with st.status("Processing your recording…", expanded=False) as status:
                result = run_screenshot_pipeline(
                    str(cache_path),
                    filename=uploaded.name,
                    change_threshold=change_threshold,
                    min_gap=min_gap,
                    sample_interval=sample_interval,
                    max_gap_sec=DEFAULT_MAX_GAP_SEC,
                    crop_left_pct=crop_margins["left"],
                    crop_right_pct=crop_margins["right"],
                    crop_top_pct=crop_margins["top"],
                    crop_bottom_pct=crop_margins["bottom"],
                    on_progress=on_progress,
                )
                status.update(label="Document ready", state="complete")
            st.session_state["last_result"] = result
            save_last_result(result)
            progress.empty()
            progress_text.empty()
            st.rerun()
        except Exception as exc:
            st.error(f"Failed: {exc}")

    result = st.session_state.get("last_result")
    pdf_path = get_result_doc_path(result) if result else None

    if pdf_path and pdf_path.is_file():
        st.success("Document ready.")
        st.download_button(
            "Download PDF",
            data=pdf_path.read_bytes(),
            file_name=pdf_path.name,
            mime="application/pdf",
            use_container_width=True,
        )

        shot_count = len(result.get("screenshots") or []) if result else 0
        m1, m2, m3 = st.columns(3)
        m1.metric("Screenshots captured", str(shot_count))
        m2.metric("Transcript segments", str(_transcript_segment_count(result)))
        m3.metric("Video duration", _video_duration_from_result(result))

        _, start_over_col = st.columns([4, 1])
        with start_over_col:
            if st.button("Start over", type="secondary", use_container_width=True):
                clear_current_result()
                st.rerun()


if __name__ == "__main__":
    run_app()
