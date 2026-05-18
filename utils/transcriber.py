"""Local transcription with faster-whisper."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

ProgressCb = Callable[[str, int], None] | None


def _format_ts(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _write_transcript(segments: list[dict], output_path: Path) -> str:
    lines: list[str] = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start = _format_ts(float(segment.get("start", 0.0)))
        end = _format_ts(float(segment.get("end", segment.get("start", 0.0))))
        lines.append(f"[{start} - {end}] {text}")

    transcript = "\n".join(lines).strip()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(transcript + ("\n" if transcript else ""), encoding="utf-8")
    return transcript


def _format_transcript(segments: list[dict]) -> str:
    lines: list[str] = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start = _format_ts(float(segment.get("start", 0.0)))
        end = _format_ts(float(segment.get("end", segment.get("start", 0.0))))
        lines.append(f"[{start} - {end}] {text}")
    return "\n".join(lines).strip()


def transcribe_video(
    video_path: str,
    *,
    model_size: str = "base",
    output_path: str | Path | None = "outputs/transcript.txt",
    on_progress: ProgressCb = None,
) -> dict:
    """Transcribe a video file locally with faster-whisper."""
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise RuntimeError(
            "faster-whisper is not installed. Run `pip install -r requirements.txt`."
        ) from exc

    if on_progress:
        on_progress("Loading faster-whisper model", 0)

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    raw_segments, info = model.transcribe(
        video_path,
        beam_size=1,
        vad_filter=True,
    )

    duration = float(getattr(info, "duration", 0.0) or 0.0)
    segments: list[dict] = []
    for raw in raw_segments:
        segment = {
            "start": float(raw.start),
            "end": float(raw.end),
            "text": str(raw.text).strip(),
        }
        segments.append(segment)
        if on_progress and duration > 0:
            pct = int(min(95, (segment["end"] / duration) * 95))
            on_progress("Transcribing audio", pct)

    if output_path is None:
        transcript_text = _format_transcript(segments)
    else:
        transcript_text = _write_transcript(segments, Path(output_path))
    if on_progress:
        on_progress("Transcript ready", 100)

    return {
        "segments": segments,
        "text": transcript_text,
        "path": str(output_path) if output_path is not None else "",
        "language": getattr(info, "language", None),
        "language_probability": float(getattr(info, "language_probability", 0.0) or 0.0),
    }
