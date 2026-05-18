"""Streamlit UI for extracting meaningful video screen changes into a PDF."""

from __future__ import annotations

import html
import json
import os
import shutil
import tempfile
from pathlib import Path

import cv2
import streamlit as st
import streamlit.components.v1 as components

from utils.pipeline import run_screenshot_pipeline

APP_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = APP_DIR / "outputs"
PROMPT_PATH = APP_DIR / "consultant_ai_prompt.md"
MAX_UPLOAD_BYTES = 2000 * 1024 * 1024

os.chdir(APP_DIR)

st.set_page_config(
    page_title="Video Screenshot PDF",
    page_icon="🎞️",
    layout="wide",
)

APP_CSS = """
<style>
  #MainMenu, footer, header {visibility: hidden;}
  html, body, [class*="css"] {
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  .stApp {
    background:
      radial-gradient(circle at top left, rgba(59,130,246,0.14), transparent 28%),
      radial-gradient(circle at top right, rgba(168,85,247,0.10), transparent 25%),
      #080808;
  }
  .block-container {
    max-width: 1100px;
    padding-top: 2.5rem;
  }
  .hero-card {
    padding: 0 0 1rem;
    border-bottom: 1px solid rgba(63,63,70,0.65);
    margin-bottom: 1.25rem;
  }
  .hero-card h1 {
    margin: 0 0 0.5rem;
    font-size: 2.5rem;
    letter-spacing: -0.04em;
  }
  .hero-card p {
    color: #a1a1aa;
    font-size: 1rem;
    line-height: 1.55;
    margin-bottom: 0;
  }
  [data-testid="stFileUploader"] section {
    background: linear-gradient(135deg, #0f0f0f, #1a1a1a);
    border: 1px dashed #3b82f6;
    border-radius: 14px;
    padding: 18px;
  }
  .stButton > button[kind="primary"],
  .stDownloadButton > button {
    border-radius: 12px;
    border: 1px solid #333;
    background: linear-gradient(135deg, #2563eb, #7c3aed);
    color: white;
    font-weight: 700;
  }
  .shot-card {
    background: linear-gradient(135deg, #0f0f0f, #1a1a1a);
    border: 1px solid #27272a;
    border-radius: 14px;
    padding: 0.8rem;
  }
  .muted {
    color: #a1a1aa;
    font-size: 0.95rem;
  }
  .section-rule {
    border: 0;
    border-top: 1px solid rgba(63,63,70,0.65);
    margin: 1.4rem 0;
  }
  .stepper {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 0.6rem;
    margin: 0.25rem 0 1.4rem;
  }
  .step-card {
    border: 1px solid #27272a;
    background: rgba(15,15,15,0.72);
    border-radius: 999px;
    padding: 0.7rem 0.85rem;
    display: flex;
    align-items: center;
    gap: 0.6rem;
  }
  .step-card.active {
    border-color: #3b82f6;
    box-shadow: 0 0 0 1px rgba(59,130,246,0.25);
  }
  .step-card.complete {
    border-color: #16a34a;
    background: rgba(22,101,52,0.16);
  }
  .step-number {
    color: #d4d4d8;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.7rem;
    height: 1.7rem;
    border-radius: 999px;
    background: #27272a;
    font-weight: 800;
    flex: 0 0 auto;
  }
  .step-card.active .step-number {
    background: #2563eb;
    color: #fff;
  }
  .step-card.complete .step-number {
    background: #16a34a;
    color: #fff;
  }
  .step-title {
    color: #f4f4f5;
    font-weight: 800;
  }
  .instruction-line {
    color: #a1a1aa;
    font-size: 0.95rem;
    margin: 0.25rem 0 1rem;
  }
  @media (max-width: 800px) {
    .stepper {
      grid-template-columns: 1fr;
    }
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
    return "Attach the screenshot PDF and transcript, then summarize the walkthrough."


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


def render_open_ai_buttons(prompt_text: str) -> None:
    prompt_payload = json.dumps(prompt_text)
    component_html = """
    <style>
      body {
        margin: 0;
        font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        background: transparent;
        color: #f4f4f5;
      }
      .ai-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.7rem;
      }
      button {
        min-height: 48px;
        border: 0;
        border-radius: 13px;
        color: white;
        cursor: pointer;
        font-weight: 800;
        padding: 0.85rem;
        width: 100%;
        box-shadow: 0 12px 28px rgba(0,0,0,0.22);
      }
      .claude { background: linear-gradient(135deg, #b45309, #f97316); }
      .chatgpt { background: linear-gradient(135deg, #047857, #10b981); }
      .gemini { background: linear-gradient(135deg, #1d4ed8, #38bdf8); }
      #toast {
        color: #bbf7d0;
        min-height: 1.3rem;
        margin-top: 0.55rem;
        font-size: 0.9rem;
      }
      @media (max-width: 780px) {
        .ai-grid { grid-template-columns: 1fr; }
      }
    </style>
    <div class="ai-grid">
      <button class="claude" title="Prompt copied! Paste it after attaching your files." onclick="openAi('https://claude.ai', 'Claude')">🟠 Claude</button>
      <button class="chatgpt" title="Prompt copied! Paste it after attaching your files." onclick="openAi('https://chatgpt.com', 'ChatGPT')">🟢 ChatGPT</button>
      <button class="gemini" title="Prompt copied! Paste it after attaching your files." onclick="openAi('https://gemini.google.com', 'Gemini')">🔵 Gemini</button>
    </div>
    <div id="toast" aria-live="polite"></div>
    <script>
      const promptText = __PROMPT_JSON__;
      const toast = document.getElementById("toast");

      function showToast(message) {
        toast.textContent = message;
      }

      async function copyPrompt(name) {
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
          showToast(`Prompt copied! Paste it into ${name} after attaching your files.`);
        } catch (error) {
          showToast("Copy failed. Select and copy the prompt from consultant_ai_prompt.md.");
        }
      }

      function openAi(url, name) {
        copyPrompt(name);
        window.open(url, "_blank", "noopener,noreferrer");
      }
    </script>
    """.replace("__PROMPT_JSON__", prompt_payload)
    components.html(component_html, height=96)


def clear_outputs() -> None:
    if OUTPUT_DIR.exists():
        shutil.rmtree(OUTPUT_DIR)
    (OUTPUT_DIR / "screenshots").mkdir(parents=True, exist_ok=True)


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
    consultant_prompt = load_consultant_prompt()
    st.markdown(
        """
        <div class="hero-card">
          <h1>Video Screenshot PDF</h1>
          <p>
            Upload a screen recording, detect meaningful visual changes, extract those
            frames as screenshots, transcribe the audio locally, and download the outputs.
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
    st.caption("Default settings work well for most videos. Expand Advanced Settings only if needed.")
    with st.expander("⚙️ Advanced Settings", expanded=False):
        st.markdown("#### Detection settings")
        col_a, col_b, col_c = st.columns(3)
        with col_a:
            change_threshold = st.slider(
                "Minimum changed area (%)",
                min_value=1.0,
                max_value=40.0,
                value=10.0,
                step=0.5,
                help="Lower values capture more screenshots. Higher values ignore smaller UI updates.",
            )
        with col_b:
            min_gap = st.slider(
                "Minimum gap between screenshots (seconds)",
                min_value=0.5,
                max_value=20.0,
                value=3.0,
                step=0.5,
            )
        with col_c:
            sample_interval = st.slider(
                "Sample every N seconds",
                min_value=0.25,
                max_value=5.0,
                value=1.0,
                step=0.25,
                help="Shorter intervals catch faster screen changes but take longer.",
            )

        st.markdown("#### Transcription settings")
        whisper_model_size = st.selectbox(
            "faster-whisper model",
            options=["tiny", "base", "small", "medium", "large-v3"],
            index=1,
            help="Larger models are more accurate but slower and heavier to run locally.",
        )

    over_size = uploaded is not None and uploaded.size > MAX_UPLOAD_BYTES
    duration = probe_upload(uploaded) if uploaded is not None and not over_size else None

    if over_size:
        st.error("File exceeds the 2 GB upload limit. Compress the video and try again.")
    elif uploaded is not None and duration is not None:
        st.success(
            f"{html.escape(uploaded.name)} is ready: {format_ts(duration)} long, "
            f"{uploaded.size / (1024 * 1024):.1f} MB."
        )

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
        clear_outputs()
        suffix = Path(uploaded.name).suffix or ".mp4"
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        os.close(tmp_fd)
        try:
            with open(tmp_path, "wb") as f:
                f.write(uploaded.getbuffer())

            progress = st.progress(0)
            progress_text = st.empty()

            def on_progress(message: str, percent: int) -> None:
                progress.progress(max(0, min(100, percent)))
                progress_text.markdown(f"**{html.escape(message)}** · {percent}%")

            with st.status("Processing video...", expanded=True) as status:
                result = run_screenshot_pipeline(
                    tmp_path,
                    filename=uploaded.name,
                    change_threshold=change_threshold,
                    min_gap=min_gap,
                    sample_interval=sample_interval,
                    whisper_model_size=whisper_model_size,
                    on_progress=on_progress,
                )
                status.update(label="Outputs ready", state="complete")

            st.session_state["last_result"] = result
        except Exception as exc:
            st.error(f"Processing failed: {exc}")
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    result = st.session_state.get("last_result")
    step_placeholder.markdown(
        render_step_indicator(uploaded, result, False),
        unsafe_allow_html=True,
    )
    if not result:
        st.info("The first frame is always included. Later frames are kept only when the screen changes enough to pass the threshold.")
        return

    st.divider()
    pdf_path = Path(result["pdf_path"])
    screenshots = result["screenshots"]
    transcript = result.get("transcript") or {}
    transcript_text = str(transcript.get("text") or "")
    transcript_path = Path(str(transcript.get("path") or ""))
    st.subheader("Step 3: Download & Open in AI")
    st.markdown(
        f'<p class="muted"><b>{len(screenshots)}</b> screenshots extracted from '
        f'<b>{html.escape(str(result["filename"]))}</b>.</p>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<p class="instruction-line">Download both files, copy the prompt, then open your preferred AI model and attach the files + paste the prompt.</p>',
        unsafe_allow_html=True,
    )

    download_cols = st.columns(2)
    with download_cols[0]:
        st.markdown("#### Screenshot PDF")
        st.caption("Attach this to your AI model")
        if pdf_path.is_file():
            st.download_button(
                "Download Screenshot PDF",
                data=pdf_path.read_bytes(),
                file_name=pdf_path.name,
                mime="application/pdf",
                use_container_width=True,
            )
    with download_cols[1]:
        st.markdown("#### Transcript")
        st.caption("Attach this to your AI model")
        if transcript_path.is_file():
            transcript_bytes = transcript_path.read_bytes()
        else:
            transcript_bytes = transcript_text.encode("utf-8")
        st.download_button(
            "Download Transcript",
            data=transcript_bytes,
            file_name="transcript.txt",
            mime="text/plain",
            use_container_width=True,
        )

    render_transcript_preview(transcript_text)

    st.markdown("#### Copy Prompt")
    render_copy_prompt_button(consultant_prompt)
    st.caption("Paste this into your AI model along with both files")

    st.caption("Open in AI")
    render_open_ai_buttons(consultant_prompt)

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
