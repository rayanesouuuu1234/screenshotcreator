"""Interactive video-frame crop selector for Streamlit."""

from __future__ import annotations

import json

import streamlit.components.v1 as components


def render_interactive_crop_selector(
    image_b64: str,
    nat_w: int,
    nat_h: int,
    initial_crop: dict[str, float],
    *,
    height: int,
) -> dict[str, float] | None:
    """Render a draggable crop box; returns margin percentages or None if unchanged."""
    initial_json = json.dumps(initial_crop)
    display_max = 920
    display_w = max(1, int(nat_w * min(1.0, display_max / max(nat_w, 1))))
    display_h = max(1, int(nat_h * display_w / max(nat_w, 1)))

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: transparent;
    color: #e5e7eb;
  }}
  .wrap {{
    display: inline-block;
    position: relative;
    max-width: 100%;
    user-select: none;
    touch-action: none;
  }}
  #frame {{
    position: relative;
    width: {display_w}px;
    height: {display_h}px;
    overflow: hidden;
    border-radius: 12px;
    border: 1px solid rgba(96, 165, 250, 0.35);
    background: #0f172a;
  }}
  #preview {{
    display: block;
    width: 100%;
    height: 100%;
    pointer-events: none;
  }}
  .shade {{
    position: absolute;
    background: rgba(0, 0, 0, 0.55);
    pointer-events: none;
  }}
  #cropBox {{
    position: absolute;
    border: 2px solid #60a5fa;
    box-shadow: 0 0 0 1px rgba(15, 23, 42, 0.65) inset;
    cursor: move;
  }}
  .handle {{
    position: absolute;
    width: 12px;
    height: 12px;
    background: #fff;
    border: 2px solid #2563eb;
    border-radius: 3px;
    z-index: 3;
  }}
  .handle.n {{ top: -7px; left: 50%; transform: translateX(-50%); cursor: n-resize; }}
  .handle.s {{ bottom: -7px; left: 50%; transform: translateX(-50%); cursor: s-resize; }}
  .handle.e {{ right: -7px; top: 50%; transform: translateY(-50%); cursor: e-resize; }}
  .handle.w {{ left: -7px; top: 50%; transform: translateY(-50%); cursor: w-resize; }}
  .handle.ne {{ top: -7px; right: -7px; cursor: ne-resize; }}
  .handle.nw {{ top: -7px; left: -7px; cursor: nw-resize; }}
  .handle.se {{ bottom: -7px; right: -7px; cursor: se-resize; }}
  .handle.sw {{ bottom: -7px; left: -7px; cursor: sw-resize; }}
  .hint {{
    margin-top: 0.65rem;
    font-size: 0.88rem;
    color: #9ca3af;
  }}
  .values {{
    margin-top: 0.35rem;
    font-size: 0.82rem;
    color: #cbd5e1;
    font-variant-numeric: tabular-nums;
  }}
</style>
</head>
<body>
  <div class="wrap" id="root">
    <div id="frame">
      <img id="preview" alt="Video preview frame" src="data:image/jpeg;base64,{image_b64}" />
      <div class="shade" id="shadeTop"></div>
      <div class="shade" id="shadeLeft"></div>
      <div class="shade" id="shadeRight"></div>
      <div class="shade" id="shadeBottom"></div>
      <div id="cropBox">
        <div class="handle n" data-handle="n"></div>
        <div class="handle s" data-handle="s"></div>
        <div class="handle e" data-handle="e"></div>
        <div class="handle w" data-handle="w"></div>
        <div class="handle ne" data-handle="ne"></div>
        <div class="handle nw" data-handle="nw"></div>
        <div class="handle se" data-handle="se"></div>
        <div class="handle sw" data-handle="sw"></div>
      </div>
    </div>
  </div>
  <div class="hint">Drag the box or corner/edge handles to crop away meeting panels or browser chrome.</div>
  <div class="values" id="values"></div>
<script>
  const DISPLAY_W = {display_w};
  const DISPLAY_H = {display_h};
  const MIN_SIZE = Math.max(40, Math.min(DISPLAY_W, DISPLAY_H) * 0.08);
  const initial = {initial_json};

  const cropBox = document.getElementById("cropBox");
  const valuesEl = document.getElementById("values");
  const shades = {{
    top: document.getElementById("shadeTop"),
    left: document.getElementById("shadeLeft"),
    right: document.getElementById("shadeRight"),
    bottom: document.getElementById("shadeBottom"),
  }};

  let x = (initial.left / 100) * DISPLAY_W;
  let y = (initial.top / 100) * DISPLAY_H;
  let w = DISPLAY_W - ((initial.left + initial.right) / 100) * DISPLAY_W;
  let h = DISPLAY_H - ((initial.top + initial.bottom) / 100) * DISPLAY_H;

  let dragMode = null;
  let startX = 0;
  let startY = 0;
  let startBox = null;

  function clampBox() {{
    w = Math.max(MIN_SIZE, Math.min(w, DISPLAY_W));
    h = Math.max(MIN_SIZE, Math.min(h, DISPLAY_H));
    x = Math.max(0, Math.min(x, DISPLAY_W - w));
    y = Math.max(0, Math.min(y, DISPLAY_H - h));
  }}

  function toPct() {{
    return {{
      left: Math.round((x / DISPLAY_W) * 1000) / 10,
      right: Math.round(((DISPLAY_W - x - w) / DISPLAY_W) * 1000) / 10,
      top: Math.round((y / DISPLAY_H) * 1000) / 10,
      bottom: Math.round(((DISPLAY_H - y - h) / DISPLAY_H) * 1000) / 10,
    }};
  }}

  function updateValuesLabel() {{
    const payload = toPct();
    valuesEl.textContent =
      "Crop margins — left: " + payload.left + "% · right: " + payload.right +
      "% · top: " + payload.top + "% · bottom: " + payload.bottom + "%";
  }}

  function sendValue() {{
    updateValuesLabel();
    const payload = toPct();
    window.parent.postMessage(
      {{
        type: "streamlit:setComponentValue",
        value: payload,
        isStreamlitMessage: true,
      }},
      "*",
    );
  }}

  function render() {{
    clampBox();
    cropBox.style.left = x + "px";
    cropBox.style.top = y + "px";
    cropBox.style.width = w + "px";
    cropBox.style.height = h + "px";

    shades.top.style.left = "0";
    shades.top.style.top = "0";
    shades.top.style.width = DISPLAY_W + "px";
    shades.top.style.height = y + "px";

    shades.left.style.left = "0";
    shades.left.style.top = y + "px";
    shades.left.style.width = x + "px";
    shades.left.style.height = h + "px";

    shades.right.style.left = (x + w) + "px";
    shades.right.style.top = y + "px";
    shades.right.style.width = (DISPLAY_W - x - w) + "px";
    shades.right.style.height = h + "px";

    shades.bottom.style.left = "0";
    shades.bottom.style.top = (y + h) + "px";
    shades.bottom.style.width = DISPLAY_W + "px";
    shades.bottom.style.height = (DISPLAY_H - y - h) + "px";
  }}

  function pointerPos(event) {{
    const rect = document.getElementById("frame").getBoundingClientRect();
    return {{
      x: event.clientX - rect.left,
      y: event.clientY - rect.top,
    }};
  }}

  function onPointerDown(event) {{
    event.preventDefault();
    const handle = event.target.getAttribute("data-handle");
    dragMode = handle || "move";
    const pos = pointerPos(event);
    startX = pos.x;
    startY = pos.y;
    startBox = {{ x: x, y: y, w: w, h: h }};
    cropBox.setPointerCapture(event.pointerId);
  }}

  function onPointerMove(event) {{
    if (!dragMode || !startBox) return;
    const pos = pointerPos(event);
    const dx = pos.x - startX;
    const dy = pos.y - startY;
    const box = startBox;

    if (dragMode === "move") {{
      x = box.x + dx;
      y = box.y + dy;
    }} else {{
      if (dragMode.indexOf("w") >= 0) {{
        x = box.x + dx;
        w = box.w - dx;
      }}
      if (dragMode.indexOf("e") >= 0) {{
        w = box.w + dx;
      }}
      if (dragMode.indexOf("n") >= 0) {{
        y = box.y + dy;
        h = box.h - dy;
      }}
      if (dragMode.indexOf("s") >= 0) {{
        h = box.h + dy;
      }}
    }}
    render();
    updateValuesLabel();
  }}

  function onPointerUp(event) {{
    if (!dragMode) return;
    dragMode = null;
    startBox = null;
    try {{ cropBox.releasePointerCapture(event.pointerId); }} catch (err) {{}}
    sendValue();
  }}

  cropBox.addEventListener("pointerdown", onPointerDown);
  cropBox.addEventListener("pointermove", onPointerMove);
  cropBox.addEventListener("pointerup", onPointerUp);
  cropBox.addEventListener("pointercancel", onPointerUp);
  render();
  updateValuesLabel();
</script>
</body>
</html>"""


    returned = components.html(html, height=height, scrolling=False)
    if returned is None:
        return None
    if isinstance(returned, str):
        try:
            returned = json.loads(returned)
        except json.JSONDecodeError:
            return None
    if not isinstance(returned, dict):
        return None
    return {
        "left": float(returned.get("left", 0.0)),
        "right": float(returned.get("right", 0.0)),
        "top": float(returned.get("top", 0.0)),
        "bottom": float(returned.get("bottom", 0.0)),
    }
