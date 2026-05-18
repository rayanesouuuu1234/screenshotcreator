# Video Screenshot PDF Generator

Streamlit app that turns a screen recording into a timestamped screenshot PDF with embedded transcript context.

## What It Does

1. Accepts a video file upload.
2. Samples frames throughout the video with OpenCV.
3. Detects significant visual changes while ignoring minor compression noise.
4. Saves the selected frames as screenshots.
5. Transcribes audio locally with faster-whisper.
6. Generates a downloadable PDF with screenshots and matching transcript context in chronological order.

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

## Optional Automation Delivery

The app can deliver the finished PDF after processing if you enable options in the **Automation delivery** expander.

- **Google Drive:** set `GOOGLE_DRIVE_FOLDER_ID` plus either `GOOGLE_SERVICE_ACCOUNT_FILE` or `GOOGLE_SERVICE_ACCOUNT_JSON`.
- **Slack:** set `SLACK_WEBHOOK_URL` or paste an incoming webhook URL in the app.
- **Email:** set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, and `SMTP_FROM`, then enter recipients in the app.

Google Drive uploads require the destination folder to be shared with the service account.

## Tuning

- **Minimum changed area (%)** controls how much of the frame must change before a screenshot is captured.
- **Minimum gap between screenshots** avoids repeated captures during animations or transitions.
- **Sample every N seconds** controls how often the video is checked. Lower values catch faster UI changes but take longer to process.
- **faster-whisper model** controls transcription accuracy and speed. `base` is a good default.

Outputs are written to `outputs/`, including individual screenshots, `screenshots.json`, and the generated PDF. Screenshot extraction is uncapped; the number of captures depends only on the detection settings and the video content.
# screenshotcreator
