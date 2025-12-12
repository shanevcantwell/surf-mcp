"""
Utility functions for Fara Test Harness.

Pure functions with no streamlit dependency - can be tested independently.
"""

import base64
import io
import json
from pathlib import Path
from typing import Optional, Tuple

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

    Only handles navigation commands that don't need Fara.
    Everything else goes to `act` and lets Fara decide.
    """
    text = text.strip()
    lower = text.lower()

    # goto url - direct navigation, no LLM needed
    if lower.startswith("goto "):
        url = text[5:].strip()
        # Auto-prepend https:// if no protocol specified
        if url and not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        return ("goto", url, None)

    # scroll - could go to Fara, but simple enough to handle directly
    if lower.startswith("scroll "):
        direction = text[7:].strip().lower()
        if direction not in ("up", "down"):
            direction = "down"
        return ("scroll", direction, None)

    # Everything else: let Fara decide what to do
    return ("act", text, None)
