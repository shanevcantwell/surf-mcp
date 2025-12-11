"""
Utility functions for Fara Test Harness.

Pure functions with no streamlit dependency - can be tested independently.
"""

import base64
import io
import json
import re
from pathlib import Path
from typing import Optional, Tuple, Any

from PIL import Image, ImageDraw


# ==================== Constants ====================

STORAGE_STATE_PATH = Path(__file__).parent / "storage" / "storage_state.json"


# ==================== Storage State ====================

def load_storage_state() -> Optional[dict]:
    """Load storage state from disk if exists."""
    if STORAGE_STATE_PATH.exists():
        try:
            return json.loads(STORAGE_STATE_PATH.read_text())
        except Exception:
            return None
    return None


def save_storage_state(state: dict) -> None:
    """Save storage state to disk."""
    STORAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORAGE_STATE_PATH.write_text(json.dumps(state, indent=2))


# ==================== Image Processing ====================

def decode_screenshot(b64_data: str) -> Image.Image:
    """Decode base64 screenshot to PIL Image."""
    img_bytes = base64.b64decode(b64_data)
    return Image.open(io.BytesIO(img_bytes))


def draw_overlay(
    image: Image.Image,
    x: Optional[int] = None,
    y: Optional[int] = None,
    confidence: Optional[float] = None,
) -> Image.Image:
    """Draw red dot and confidence on screenshot."""
    if x is None or y is None:
        return image

    img = image.copy()
    draw = ImageDraw.Draw(img)

    # Draw red circle at coordinates
    radius = 15
    draw.ellipse(
        [(x - radius, y - radius), (x + radius, y + radius)],
        fill="red",
        outline="white",
        width=2,
    )

    # Draw crosshair
    line_len = 25
    draw.line([(x - line_len, y), (x + line_len, y)], fill="white", width=2)
    draw.line([(x, y - line_len), (x, y + line_len)], fill="white", width=2)

    # Draw confidence label
    if confidence is not None:
        label = f"{confidence:.2f}"
        # Draw background for text
        draw.rectangle([(x + 20, y - 10), (x + 70, y + 10)], fill="black")
        draw.text((x + 25, y - 8), label, fill="white")

    return img


# ==================== Command Parsing ====================

def parse_command(text: str) -> Tuple[str, str, Optional[str]]:
    """
    Parse user command into (action, target, extra).

    Supports:
    - locate "description"
    - click "description"
    - type "description" text to type
    - goto url
    - scroll up/down
    """
    text = text.strip()

    # goto url
    if text.lower().startswith("goto "):
        url = text[5:].strip()
        return ("goto", url, None)

    # scroll direction
    if text.lower().startswith("scroll "):
        direction = text[7:].strip().lower()
        if direction not in ("up", "down"):
            direction = "down"
        return ("scroll", direction, None)

    # locate "description"
    match = re.match(r'locate\s+["\'](.+?)["\']', text, re.IGNORECASE)
    if match:
        return ("locate", match.group(1), None)

    # click "description"
    match = re.match(r'click\s+["\'](.+?)["\']', text, re.IGNORECASE)
    if match:
        return ("click", match.group(1), None)

    # type "description" text
    match = re.match(r'type\s+["\'](.+?)["\']\s+(.+)', text, re.IGNORECASE)
    if match:
        return ("type", match.group(1), match.group(2))

    # Default: treat as locate
    return ("locate", text, None)
