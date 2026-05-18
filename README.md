# Video Screenshot PDF Generator

Streamlit app that turns a screen recording into a compact timestamped screenshot PDF and a downloadable transcript.

## What It Does

1. Accepts a video file upload.
2. Samples frames throughout the video with OpenCV.
3. Detects significant visual changes while ignoring minor compression noise.
4. Saves the selected frames as screenshots.
5. Generates a downloadable PDF with screenshots in chronological order, packed multiple per page when possible.
6. Transcribes audio locally with faster-whisper and writes a downloadable `transcript.txt`.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
streamlit run app.py
```

## Tuning

- **Minimum changed area (%)** controls how much of the frame must change before a screenshot is captured.
- **Minimum gap between screenshots** avoids repeated captures during animations or transitions.
- **Sample every N seconds** controls how often the video is checked. Lower values catch faster UI changes but take longer to process.
- **faster-whisper model** controls transcription accuracy and speed. `base` is a good default.

Outputs are written to `outputs/`, including individual screenshots, `screenshots.json`, `transcript.txt`, and the generated PDF. Screenshot extraction is uncapped; the number of captures depends only on the detection settings and the video content.
# screenshotcreator
