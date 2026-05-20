"""Bounded drag crop using Streamlit v2 components (no external CDN)."""

from __future__ import annotations

import streamlit as st

_CROP_HTML = """
<div class="crop-wrap">
  <div id="crop-frame">
    <img id="crop-preview" alt="Video frame" />
    <div class="shade" id="shade-top"></div>
    <div class="shade" id="shade-left"></div>
    <div class="shade" id="shade-right"></div>
    <div class="shade" id="shade-bottom"></div>
    <div id="crop-box">
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
"""

_CROP_CSS = """
.crop-wrap {
  display: flex;
  justify-content: center;
  width: 100%;
  user-select: none;
  touch-action: none;
}
#crop-frame {
  position: relative;
  overflow: hidden;
  border-radius: 14px;
  border: 1px solid rgba(96, 165, 250, 0.4);
  background: #0f172a;
  box-shadow: 0 16px 40px rgba(0, 0, 0, 0.35);
}
#crop-preview {
  display: block;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
.shade {
  position: absolute;
  background: rgba(2, 6, 23, 0.62);
  pointer-events: none;
}
#crop-box {
  position: absolute;
  border: 2px solid #38bdf8;
  cursor: move;
  box-sizing: border-box;
}
.handle {
  position: absolute;
  width: 11px;
  height: 11px;
  background: #fff;
  border: 2px solid #2563eb;
  border-radius: 2px;
  z-index: 3;
}
.handle.n { top: -6px; left: 50%; transform: translateX(-50%); cursor: n-resize; }
.handle.s { bottom: -6px; left: 50%; transform: translateX(-50%); cursor: s-resize; }
.handle.e { right: -6px; top: 50%; transform: translateY(-50%); cursor: e-resize; }
.handle.w { left: -6px; top: 50%; transform: translateY(-50%); cursor: w-resize; }
.handle.ne { top: -6px; right: -6px; cursor: ne-resize; }
.handle.nw { top: -6px; left: -6px; cursor: nw-resize; }
.handle.se { bottom: -6px; right: -6px; cursor: se-resize; }
.handle.sw { bottom: -6px; left: -6px; cursor: sw-resize; }
"""

_CROP_JS = """
let displayW = 1;
let displayH = 1;
let minSize = 48;
let x = 0;
let y = 0;
let w = 1;
let h = 1;
let dragMode = null;
let startX = 0;
let startY = 0;
let startBox = null;

function initFromMargins(margins) {
  const crop = margins || { left: 0, right: 0, top: 0, bottom: 0 };
  x = (crop.left / 100) * displayW;
  y = (crop.top / 100) * displayH;
  w = displayW - ((crop.left + crop.right) / 100) * displayW;
  h = displayH - ((crop.top + crop.bottom) / 100) * displayH;
}

function clampBox() {
  w = Math.max(minSize, Math.min(w, displayW));
  h = Math.max(minSize, Math.min(h, displayH));
  x = Math.max(0, Math.min(x, displayW - w));
  y = Math.max(0, Math.min(y, displayH - h));
}

function toPct() {
  return {
    left: Math.round((x / displayW) * 1000) / 10,
    right: Math.round(((displayW - x - w) / displayW) * 1000) / 10,
    top: Math.round((y / displayH) * 1000) / 10,
    bottom: Math.round(((displayH - y - h) / displayH) * 1000) / 10,
  };
}

function renderCrop(frame, cropBox, shades) {
  clampBox();
  cropBox.style.left = x + "px";
  cropBox.style.top = y + "px";
  cropBox.style.width = w + "px";
  cropBox.style.height = h + "px";

  shades.top.style.left = "0";
  shades.top.style.top = "0";
  shades.top.style.width = displayW + "px";
  shades.top.style.height = y + "px";

  shades.left.style.left = "0";
  shades.left.style.top = y + "px";
  shades.left.style.width = x + "px";
  shades.left.style.height = h + "px";

  shades.right.style.left = (x + w) + "px";
  shades.right.style.top = y + "px";
  shades.right.style.width = (displayW - x - w) + "px";
  shades.right.style.height = h + "px";

  shades.bottom.style.left = "0";
  shades.bottom.style.top = (y + h) + "px";
  shades.bottom.style.width = displayW + "px";
  shades.bottom.style.height = (displayH - y - h) + "px";
}

function pointerPos(frame, event) {
  const rect = frame.getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(displayW, event.clientX - rect.left)),
    y: Math.max(0, Math.min(displayH, event.clientY - rect.top)),
  };
}

export default function(component) {
  const { parentElement, data, setStateValue } = component;
  if (!data) return;

  const frame = parentElement.querySelector("#crop-frame");
  const preview = parentElement.querySelector("#crop-preview");
  const cropBox = parentElement.querySelector("#crop-box");
  if (!frame || !preview || !cropBox) return;

  const shades = {
    top: parentElement.querySelector("#shade-top"),
    left: parentElement.querySelector("#shade-left"),
    right: parentElement.querySelector("#shade-right"),
    bottom: parentElement.querySelector("#shade-bottom"),
  };

  const initToken = String(data.init_token || "");
  if (frame.dataset.initToken !== initToken) {
    frame.dataset.initToken = initToken;
    displayW = Math.max(1, Number(data.display_w || 1));
    displayH = Math.max(1, Number(data.display_h || 1));
    minSize = Math.max(48, Math.min(displayW, displayH) * 0.1);
    frame.style.width = displayW + "px";
    frame.style.height = displayH + "px";
    if (data.image_b64) {
      preview.src = "data:image/jpeg;base64," + data.image_b64;
    }
    initFromMargins(data.margins);
    renderCrop(frame, cropBox, shades);
    setStateValue("margins", toPct());
  }

  if (frame.dataset.listeners !== "1") {
    frame.dataset.listeners = "1";

    function onPointerDown(event) {
      event.preventDefault();
      const handle = event.target.getAttribute("data-handle");
      dragMode = handle || "move";
      const pos = pointerPos(frame, event);
      startX = pos.x;
      startY = pos.y;
      startBox = { x: x, y: y, w: w, h: h };
      cropBox.setPointerCapture(event.pointerId);
    }

    function onPointerMove(event) {
      if (!dragMode || !startBox) return;
      const pos = pointerPos(frame, event);
      const dx = pos.x - startX;
      const dy = pos.y - startY;
      const box = startBox;

      if (dragMode === "move") {
        x = box.x + dx;
        y = box.y + dy;
      } else {
        if (dragMode.indexOf("w") >= 0) {
          x = box.x + dx;
          w = box.w - dx;
        }
        if (dragMode.indexOf("e") >= 0) {
          w = box.w + dx;
        }
        if (dragMode.indexOf("n") >= 0) {
          y = box.y + dy;
          h = box.h - dy;
        }
        if (dragMode.indexOf("s") >= 0) {
          h = box.h + dy;
        }
      }
      renderCrop(frame, cropBox, shades);
    }

    function onPointerUp(event) {
      if (!dragMode) return;
      dragMode = null;
      startBox = null;
      try { cropBox.releasePointerCapture(event.pointerId); } catch (err) {}
      renderCrop(frame, cropBox, shades);
      setStateValue("margins", toPct());
    }

    cropBox.addEventListener("pointerdown", onPointerDown);
    cropBox.addEventListener("pointermove", onPointerMove);
    cropBox.addEventListener("pointerup", onPointerUp);
    cropBox.addEventListener("pointercancel", onPointerUp);
  }
}
"""

_crop_component = st.components.v2.component(
    "video_crop_bounds",
    html=_CROP_HTML,
    css=_CROP_CSS,
    js=_CROP_JS,
    isolate_styles=False,
)


def render_interactive_crop_selector(
    image_b64: str,
    nat_w: int,
    nat_h: int,
    initial_crop: dict[str, float],
    *,
    height: int,
    init_token: str = "",
    key: str = "video_crop_selector",
) -> dict[str, float] | None:
    display_max = 920
    display_w = max(1, int(nat_w * min(1.0, display_max / max(nat_w, 1))))
    display_h = max(1, int(nat_h * display_w / max(nat_w, 1)))

    result = _crop_component(
        key=key,
        data={
            "image_b64": image_b64,
            "display_w": display_w,
            "display_h": display_h,
            "margins": initial_crop,
            "init_token": init_token,
        },
        default={"margins": initial_crop},
        on_margins_change=lambda: None,
        height=height,
    )
    margins = getattr(result, "margins", None)
    if not isinstance(margins, dict):
        return None
    return {
        "left": float(margins.get("left", 0.0)),
        "right": float(margins.get("right", 0.0)),
        "top": float(margins.get("top", 0.0)),
        "bottom": float(margins.get("bottom", 0.0)),
    }
