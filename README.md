# Screenshot Document Generator

Turns a walkthrough screen recording into a **PDF** with packed, timestamped screenshots and a dense transcript appendix (optimized for AI consumption).

## Output

- Multiple screenshots per page when they fit; single shots scale up to fill the page
- Per-shot transcript captions and a full transcript appendix
- No bundled AI prompts; consultants use the document in their own FDD workflow

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

## Controls

| Control | Effect |
|---------|--------|
| **Crop** | Optional trim sliders (left/right/top/bottom %) with live preview |

Upload a video and click **Generate**. Detection settings use built-in defaults.

Outputs: `outputs/screenshots/`, `outputs/screenshots.json`, generated `.pdf`.
