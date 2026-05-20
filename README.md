# Screenshot Document Generator

Turns a walkthrough screen recording into a **PDF** with packed, timestamped screenshots and a dense transcript appendix (optimized for AI consumption).

## Output

- Multiple screenshots per page when they fit; single shots scale up to fill the page
- Transcript appendix — small type, fills each page before continuing
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
| **Sensitivity** | Higher = fewer screenshots (compares vs last saved frame; tuned for white UIs) |
| **Minimum seconds between screenshots** | Reduces duplicates during animations |
| **Check every (seconds)** | Sample rate (default 0.5s) |
| **Crop** | Optional trim sliders (left/right/top/bottom %) with live preview |

Outputs: `outputs/screenshots/`, `outputs/screenshots.json`, generated `.pdf`.
