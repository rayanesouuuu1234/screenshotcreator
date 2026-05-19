"""Streamlit UI for extracting meaningful video screen changes into a Word document."""

from __future__ import annotations

import html
import importlib
import json
import os
import shutil
import tempfile
from pathlib import Path

import cv2
import streamlit as st
import streamlit.components.v1 as components

from utils.crop_ui import get_crop_margins, render_video_crop_ui, reset_crop_margins

import utils.pipeline as pipeline_module
import utils.scene_detector as scene_detector_module

scene_detector_module = importlib.reload(scene_detector_module)
pipeline_module = importlib.reload(pipeline_module)
run_screenshot_pipeline = pipeline_module.run_screenshot_pipeline

APP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = APP_DIR / "outputs"
UPLOAD_CACHE_DIR = APP_DIR / ".upload_cache"
LAST_RESULT_PATH = OUTPUT_DIR / "last_result.json"
PROMPT_PATH = APP_DIR / "consultant_ai_prompt.md"
MAX_UPLOAD_BYTES = 2000 * 1024 * 1024
os.chdir(APP_DIR)

st.set_page_config(
    page_title="Video Screenshot Document",
    page_icon="logo.jpeg",
    layout="wide",
)

APP_CSS = """
<style>
  #MainMenu, footer, header {
    visibility: hidden;
  }
  :root {
    --bg: #07080c;
    --surface: rgba(15, 18, 28, 0.78);
    --surface-strong: rgba(22, 26, 39, 0.92);
    --border: rgba(148, 163, 184, 0.16);
    --border-strong: rgba(96, 165, 250, 0.38);
    --text: #f8fafc;
    --muted: #9ca3af;
    --muted-strong: #cbd5e1;
    --blue: #60a5fa;
    --violet: #8b5cf6;
    --green: #22c55e;
    --shadow: 0 22px 70px rgba(0, 0, 0, 0.42);
  }
  @keyframes fadeUp {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
  }
  @keyframes glowPulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(96, 165, 250, 0.18); }
    50% { box-shadow: 0 0 0 7px rgba(96, 165, 250, 0.02); }
  }
  html, body, [class*="css"] {
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  .stApp {
    background:
      radial-gradient(circle at 12% 0%, rgba(96, 165, 250, 0.18), transparent 28%),
      radial-gradient(circle at 88% 4%, rgba(139, 92, 246, 0.16), transparent 30%),
      linear-gradient(180deg, #0b1020 0%, var(--bg) 42%, #050609 100%);
    color: var(--text);
  }
  .block-container {
    max-width: 1100px;
    padding-top: 2.25rem;
    padding-bottom: 4rem;
    animation: fadeUp 360ms ease-out;
  }
  .hero-card {
    position: relative;
    overflow: hidden;
    background:
      linear-gradient(135deg, rgba(15, 23, 42, 0.92), rgba(17, 24, 39, 0.78)),
      radial-gradient(circle at top right, rgba(96, 165, 250, 0.22), transparent 32%);
    border: 1px solid var(--border);
    border-radius: 28px;
    padding: 2rem 2.25rem;
    box-shadow: var(--shadow);
    margin-bottom: 1.25rem;
  }
  .hero-card h1 {
    margin: 0 0 0.5rem;
    font-size: clamp(2.2rem, 5vw, 3.45rem);
    line-height: 1;
    letter-spacing: -0.06em;
    color: var(--text);
  }
  .hero-card p {
    color: var(--muted-strong);
    font-size: 1.02rem;
    line-height: 1.65;
    margin-bottom: 0;
    max-width: 760px;
  }
  [data-testid="stFileUploader"] section {
    background: linear-gradient(135deg, rgba(15, 23, 42, 0.84), rgba(30, 41, 59, 0.55));
    border: 1px dashed rgba(96, 165, 250, 0.56);
    border-radius: 20px;
    padding: 1.2rem;
    transition: border-color 180ms ease, background 180ms ease, transform 180ms ease;
  }
  [data-testid="stFileUploader"] section:hover {
    border-color: rgba(147, 197, 253, 0.9);
    background: linear-gradient(135deg, rgba(30, 41, 59, 0.9), rgba(15, 23, 42, 0.78));
    transform: translateY(-1px);
  }
  .stButton > button[kind="primary"],
  .stDownloadButton > button {
    min-height: 3rem;
    border-radius: 16px;
    border: 1px solid rgba(147, 197, 253, 0.28);
    background: linear-gradient(135deg, #2563eb 0%, #7c3aed 100%);
    color: white;
    font-weight: 800;
    letter-spacing: -0.01em;
    box-shadow: 0 14px 34px rgba(37, 99, 235, 0.28);
    transition: transform 160ms ease, box-shadow 160ms ease, filter 160ms ease;
  }
  .stButton > button[kind="primary"]:hover,
  .stDownloadButton > button:hover {
    transform: translateY(-1px);
    filter: brightness(1.08);
    box-shadow: 0 20px 45px rgba(37, 99, 235, 0.34);
  }
  .stButton > button:not([kind="primary"]) {
    border-radius: 14px;
    border: 1px solid var(--border);
    background: rgba(15, 23, 42, 0.78);
    color: var(--text);
    transition: border-color 160ms ease, transform 160ms ease;
  }
  .shot-card {
    background: linear-gradient(135deg, rgba(15, 23, 42, 0.82), rgba(17, 24, 39, 0.76));
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 0.8rem;
    box-shadow: 0 16px 40px rgba(0, 0, 0, 0.26);
  }
  .muted {
    color: var(--muted);
    font-size: 0.95rem;
  }
  .stepper {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.6rem;
    margin: 1rem 0 1.55rem;
  }
  .step-card {
    border: 1px solid var(--border);
    background: rgba(15, 23, 42, 0.7);
    border-radius: 999px;
    padding: 0.72rem 0.9rem;
    display: flex;
    align-items: center;
    gap: 0.6rem;
    backdrop-filter: blur(18px);
  }
  .step-card.active {
    border-color: var(--border-strong);
    animation: glowPulse 2.4s ease-in-out infinite;
  }
  .step-card.complete {
    border-color: rgba(34, 197, 94, 0.42);
    background: rgba(20, 83, 45, 0.24);
  }
  .step-number {
    color: #dbeafe;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.7rem;
    height: 1.7rem;
    border-radius: 999px;
    background: rgba(51, 65, 85, 0.92);
    font-weight: 800;
    flex: 0 0 auto;
  }
  .step-card.active .step-number {
    background: linear-gradient(135deg, var(--blue), var(--violet));
    color: #fff;
  }
  .step-card.complete .step-number {
    background: var(--green);
    color: #fff;
  }
  .step-title {
    color: var(--text);
    font-weight: 800;
  }
  .project-instructions {
    color: #dbeafe;
    font-size: 1.06rem;
    line-height: 1.7;
    background: linear-gradient(135deg, rgba(37, 99, 235, 0.14), rgba(124, 58, 237, 0.12));
    border: 1px solid rgba(96, 165, 250, 0.24);
    border-radius: 18px;
    padding: 1rem 1.1rem;
    margin: 0.35rem 0 1.15rem;
  }
  [data-testid="stExpander"] {
    border: 1px solid var(--border);
    border-radius: 18px;
    background: rgba(15, 23, 42, 0.58);
    overflow: hidden;
  }
  div[data-testid="stSlider"] {
    padding-top: 0.25rem;
  }
  hr {
    border-color: rgba(148, 163, 184, 0.16);
    margin: 1.6rem 0;
  }
  h2, h3, h4 {
    color: var(--text);
    letter-spacing: -0.035em;
  }
  @media (max-width: 800px) {
    .stepper { grid-template-columns: 1fr; }
  }
</style>
"""


def get_video_duration(path: str) -> float:
    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        cap.release()
        return 0.0
    fps = cap.get(cv2.CAP_PROP_FPS) or 0.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if fps > 0 and frame_count > 0:
        duration = float(frame_count) / float(fps)
        cap.release()
        return duration
    cap.set(cv2.CAP_PROP_POS_MSEC, 1e9)
    cap.read()
    pos_ms = cap.get(cv2.CAP_PROP_POS_MSEC) or 0.0
    cap.release()
    return float(pos_ms) / 1000.0 if pos_ms > 0 else 0.0


def format_ts(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def load_consultant_prompt() -> str:
    if PROMPT_PATH.is_file():
        return PROMPT_PATH.read_text(encoding="utf-8")
    return "Attach the screenshot Word document and transcript, then summarize the walkthrough."


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
        st.session_state["restored_last_result"] = True


def save_last_result(result: dict) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    LAST_RESULT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")


def clear_current_result() -> None:
    st.session_state.pop("last_result", None)
    st.session_state.pop("restored_last_result", None)
    st.session_state.pop("upload_cache_key", None)
    st.session_state.pop("crop_pct", None)
    st.session_state.pop("crop_preview_key", None)
    st.session_state.pop("crop_preview_bgr", None)
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


def render_step_indicator(uploaded, result: dict | None, is_processing: bool = False) -> str:
    if result:
        states = ["complete", "complete", "complete"]
    elif is_processing:
        states = ["complete", "active", "pending"]
    elif uploaded is not None:
        states = ["complete", "active", "pending"]
    else:
        states = ["active", "pending", "pending"]

    titles = ["Upload", "Generate", "Download"]
    cards = []
    for idx, (title, state) in enumerate(zip(titles, states), start=1):
        cards.append(
            '<div class="step-card {state}">'
            '<div class="step-number">{idx}</div>'
            '<div class="step-title">{title}</div>'
            "</div>".format(state=state, idx=idx, title=html.escape(title))
        )
    return f'<div class="stepper">{"".join(cards)}</div>'


def render_transcript_preview(transcript_text: str) -> None:
    with st.expander("📄 Preview Transcript", expanded=False):
        if transcript_text:
            st.text_area(
                "Transcript text",
                value=transcript_text,
                height=200,
                disabled=True,
                label_visibility="collapsed",
            )
        else:
            st.info("No transcript text was produced. The video may not contain speech or readable audio.")


def render_copy_prompt_button(prompt_text: str) -> None:
    prompt_payload = json.dumps(prompt_text)
    component_html = """
    <style>
      body {
        margin: 0;
        font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: transparent;
        color: #f4f4f5;
      }
      button {
        min-height: 46px;
        border: 0;
        border-radius: 13px;
        color: white;
        cursor: pointer;
        font-weight: 800;
        padding: 0.8rem 1rem;
        width: 100%;
        box-shadow: 0 12px 28px rgba(0,0,0,0.22);
      }
      .copy { background: linear-gradient(135deg, #2563eb, #7c3aed); }
      #toast {
        color: #bbf7d0;
        min-height: 1.3rem;
        margin-top: 0.55rem;
        font-size: 0.9rem;
      }
    </style>
    <button class="copy" onclick="copyPrompt()">📋 Copy Prompt</button>
    <div id="toast" aria-live="polite"></div>
    <script>
      const promptText = __PROMPT_JSON__;
      const toast = document.getElementById("toast");

      function showToast(message) {
        toast.textContent = message;
      }

      async function copyPrompt() {
        try {
          if (navigator.clipboard && window.isSecureContext) {
            await navigator.clipboard.writeText(promptText);
          } else {
            const textarea = document.createElement("textarea");
            textarea.value = promptText;
            textarea.style.position = "fixed";
            textarea.style.opacity = "0";
            document.body.appendChild(textarea);
            textarea.focus();
            textarea.select();
            document.execCommand("copy");
            textarea.remove();
          }
          showToast("Prompt copied.");
        } catch (error) {
          showToast("Copy failed. Select and copy the prompt from consultant_ai_prompt.md.");
        }
      }
    </script>
    """.replace("__PROMPT_JSON__", prompt_payload)
    components.html(component_html, height=92)


def probe_upload(uploaded_file) -> float | None:
    if uploaded_file is None:
        return None
    suffix = Path(uploaded_file.name).suffix or ".mp4"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    os.close(tmp_fd)
    try:
        with open(tmp_path, "wb") as f:
            f.write(uploaded_file.getbuffer())
        return get_video_duration(tmp_path)
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def run_app() -> None:
    st.markdown(APP_CSS, unsafe_allow_html=True)
    restore_last_result()
    consultant_prompt = load_consultant_prompt()
    st.markdown(
        """
        <div class="hero-card">
          <h1>Video Screenshot Document</h1>
          <p>
            Upload a screen recording, optionally crop the frame, detect meaningful visual changes,
            and download a Word document with timestamped screenshots and transcript text.
          </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    step_placeholder = st.empty()

    st.subheader("Step 1: Upload your video")
    uploaded = st.file_uploader(
        "Upload a video file",
        type=["mp4", "mov", "m4v", "avi", "mkv", "webm"],
    )
    st.divider()

    st.subheader("Step 2: Configure & Generate")
    change_threshold = st.slider(
        "Screenshot sensitivity — Higher = fewer screenshots · Lower = more screenshots",
        min_value=1.0,
        max_value=40.0,
        value=10.0,
        step=0.5,
        help="Adjusts how much the screen must change before a screenshot is captured.",
    )
    st.caption(f"Current sensitivity threshold: {change_threshold:.1f}% changed area")

    over_size = uploaded is not None and uploaded.size > MAX_UPLOAD_BYTES
    duration = probe_upload(uploaded) if uploaded is not None and not over_size else None

    if over_size:
        st.error("File exceeds the 2 GB upload limit. Compress the video and try again.")
    elif uploaded is not None and duration is not None:
        st.success(
            f"{html.escape(uploaded.name)} is ready: {format_ts(duration)} long, "
            f"{uploaded.size / (1024 * 1024):.1f} MB."
        )
        cache_path = ensure_upload_cached(uploaded)
        if cache_path is not None:
            crop_margins = render_video_crop_ui(cache_path)
            st.session_state["crop_margins_for_pipeline"] = crop_margins
        else:
            st.warning("Could not read a preview frame from the video. Screenshots will use the full frame.")
            reset_crop_margins()

    run = st.button(
        "Generate",
        type="primary",
        use_container_width=True,
        disabled=uploaded is None or over_size,
    )

    existing_result = st.session_state.get("last_result")
    step_placeholder.markdown(
        render_step_indicator(uploaded, existing_result, run and uploaded is not None),
        unsafe_allow_html=True,
    )

    if run and uploaded is not None:
        cache_path = ensure_upload_cached(uploaded)
        if cache_path is None or not cache_path.is_file():
            st.error("Could not cache the uploaded video.")
            return
        clear_outputs()

        progress = st.progress(0)
        progress_text = st.empty()

        def on_progress(message: str, percent: int) -> None:
            progress.progress(max(0, min(100, percent)))
            progress_text.markdown(f"**{html.escape(message)}** · {percent}%")

        crop_margins = st.session_state.get("crop_margins_for_pipeline") or get_crop_margins()
        if any(crop_margins.get(side, 0) > 0 for side in ("left", "right", "top", "bottom")):
            st.caption(
                f"Applying crop — left {crop_margins['left']:.1f}% · right {crop_margins['right']:.1f}% · "
                f"top {crop_margins['top']:.1f}% · bottom {crop_margins['bottom']:.1f}%"
            )
        try:
            with st.status("Processing video...", expanded=True) as status:
                result = run_screenshot_pipeline(
                    str(cache_path),
                    filename=uploaded.name,
                    change_threshold=change_threshold,
                    crop_left_pct=crop_margins["left"],
                    crop_right_pct=crop_margins["right"],
                    crop_top_pct=crop_margins["top"],
                    crop_bottom_pct=crop_margins["bottom"],
                    on_progress=on_progress,
                )
                status.update(label="Outputs ready", state="complete")

            st.session_state["last_result"] = result
            save_last_result(result)
        except Exception as exc:
            st.error(f"Processing failed: {exc}")

    result = st.session_state.get("last_result")
    step_placeholder.markdown(
        render_step_indicator(uploaded, result, False),
        unsafe_allow_html=True,
    )

    if result:
        captured_count = len(result.get("screenshots") or [])
        skipped_count = int(result.get("skipped_empty_frames") or 0)
        if st.session_state.get("restored_last_result"):
            st.info("Restored your last processed result from disk.")
        st.success(
            f"✓ {captured_count} screenshots captured · "
            f"{skipped_count} skipped (blank or black frames)"
        )
        if st.button("Start over / clear current result", use_container_width=True):
            clear_current_result()
            st.rerun()

    if not result:
        st.info(
            "The first frame is always included. Later frames are kept only when the screen "
            "changes enough to pass the threshold."
        )
        return

    st.divider()
    docx_path = get_result_doc_path(result)
    screenshots = result["screenshots"]
    transcript = result.get("transcript") or {}
    transcript_text = str(transcript.get("text") or "")

    st.subheader("Step 3: Download")
    st.markdown(
        f'<p class="muted"><b>{len(screenshots)}</b> screenshots extracted from '
        f'<b>{html.escape(str(result["filename"]))}</b>.</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        """
        <div class="project-instructions">
          Create a project in your AI model of choice and paste your analysis prompt into the project instructions.
          Each session, attach the generated Word document and your reference Functional Design Document template if available.
          The document contains timestamped screenshots, transcript text, and AI instructions for producing a consultant deliverable.
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("#### Screenshot Word document")
    st.caption("Transcript context and AI instructions are embedded in this document.")
    if docx_path and docx_path.is_file():
        st.download_button(
            "Download Word Document",
            data=docx_path.read_bytes(),
            file_name=docx_path.name,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True,
        )

    render_transcript_preview(transcript_text)

    st.markdown("#### Copy Prompt")
    render_copy_prompt_button(consultant_prompt)
    st.caption("Paste this into your AI model along with the Word document.")

    if screenshots:
        st.divider()
        st.markdown("### Screenshots")
        cols_per_row = 3
        for start in range(0, len(screenshots), cols_per_row):
            cols = st.columns(cols_per_row)
            for offset, col in enumerate(cols):
                shot_idx = start + offset
                if shot_idx >= len(screenshots):
                    break
                shot = screenshots[shot_idx]
                path = Path(str(shot["path"]))
                with col:
                    st.markdown('<div class="shot-card">', unsafe_allow_html=True)
                    if path.is_file():
                        st.image(str(path), use_container_width=True)
                    st.caption(f'{shot["label"]} · change score {shot.get("change_percent", 0):.1f}%')
                    st.markdown("</div>", unsafe_allow_html=True)


if __name__ == "__main__":
    run_app()
