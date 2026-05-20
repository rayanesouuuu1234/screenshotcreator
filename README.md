# Screenshot Document Generator

Turns a walkthrough screen recording into a Word document with **large, timestamped screenshots** and a **paginated transcript** at the end (optimized for AI / PDF export).

## Output

- One screenshot per page (maximized on the page) with a timestamp heading
- Transcript appendix at the bottom — small type, fills each page before continuing
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
| **Crop** | Optional frame trim applied to all captures |

Outputs: `outputs/screenshots/`, `outputs/screenshots.json`, generated `.docx`.
