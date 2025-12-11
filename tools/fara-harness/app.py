"""
Fara Test Harness - Streamlit UI for visual grounding experimentation.

Run with: streamlit run app.py

Per ADR-003: Interactive harness for testing Fara visual grounding
through MCP exclusively (no direct imports from navigator-mcp).
"""

import base64
import io
import json
import re
from pathlib import Path
from typing import Optional, Tuple

import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from mcp_client import SyncNavigatorClient

# ==================== Constants ====================

STORAGE_STATE_PATH = Path(__file__).parent / "storage" / "storage_state.json"
DEFAULT_URL = "https://www.google.com"


# ==================== Helper Functions ====================

def load_storage_state() -> Optional[dict]:
    """Load storage state from disk if exists."""
    if STORAGE_STATE_PATH.exists():
        try:
            return json.loads(STORAGE_STATE_PATH.read_text())
        except Exception as e:
            st.warning(f"Failed to load storage state: {e}")
    return None


def save_storage_state(state: dict) -> None:
    """Save storage state to disk."""
    STORAGE_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORAGE_STATE_PATH.write_text(json.dumps(state, indent=2))


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


def parse_command(text: str) -> Tuple[str, str, Optional[str]]:
    """
    Parse user command into (action, description, extra).

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


# ==================== Session State ====================

def init_session_state():
    """Initialize Streamlit session state."""
    if "client" not in st.session_state:
        st.session_state.client = None
    if "session_id" not in st.session_state:
        st.session_state.session_id = None
    if "screenshot" not in st.session_state:
        st.session_state.screenshot = None
    if "history" not in st.session_state:
        st.session_state.history = []
    if "last_locate" not in st.session_state:
        st.session_state.last_locate = None
    if "connected" not in st.session_state:
        st.session_state.connected = False


def add_to_history(entry: str):
    """Add entry to chat history."""
    st.session_state.history.append(entry)
    # Keep last 100 entries
    if len(st.session_state.history) > 100:
        st.session_state.history = st.session_state.history[-100:]


# ==================== Main UI ====================

def main():
    st.set_page_config(
        page_title="Fara Test Harness",
        page_icon="🎯",
        layout="wide",
    )

    init_session_state()

    st.title("🎯 Fara Test Harness")
    st.caption("Visual grounding experimentation via MCP")

    # ==================== Sidebar: Connection & URL ====================
    with st.sidebar:
        st.header("Connection")

        if not st.session_state.connected:
            if st.button("Connect to Navigator MCP"):
                try:
                    client = SyncNavigatorClient()
                    client.connect()

                    # Load storage state if exists
                    storage_state = load_storage_state()

                    result = client.session_create(
                        headless=False,
                        storage_state=storage_state,
                    )

                    if "error" in result:
                        st.error(f"Failed to create session: {result['error']}")
                    else:
                        st.session_state.client = client
                        st.session_state.session_id = result["session_id"]
                        st.session_state.connected = True
                        add_to_history(f"✓ Connected: session={result['session_id']}")
                        st.rerun()

                except Exception as e:
                    st.error(f"Connection failed: {e}")
        else:
            st.success(f"Connected: {st.session_state.session_id}")

            if st.button("Disconnect"):
                try:
                    result = st.session_state.client.session_destroy(
                        st.session_state.session_id
                    )
                    # Save storage state
                    if "summary" in result:
                        web_summary = result["summary"].get("web", {})
                        if "storage_state" in web_summary:
                            save_storage_state(web_summary["storage_state"])
                            add_to_history("✓ Storage state saved")

                    st.session_state.client.disconnect()
                except Exception as e:
                    st.warning(f"Disconnect error: {e}")
                finally:
                    st.session_state.client = None
                    st.session_state.session_id = None
                    st.session_state.connected = False
                    st.session_state.screenshot = None
                    add_to_history("✓ Disconnected")
                    st.rerun()

        st.divider()

        # URL Navigation
        st.header("Navigation")
        url = st.text_input("URL", value=DEFAULT_URL)
        if st.button("Navigate", disabled=not st.session_state.connected):
            try:
                result = st.session_state.client.goto(
                    st.session_state.session_id, url
                )
                if "error" in result:
                    add_to_history(f"✗ goto failed: {result['error']}")
                else:
                    add_to_history(f"> goto {url}")
                    if "snapshot" in result:
                        st.session_state.screenshot = result["snapshot"]
                    st.session_state.last_locate = None
                    st.rerun()
            except Exception as e:
                add_to_history(f"✗ Error: {e}")

        if st.button("Refresh Screenshot", disabled=not st.session_state.connected):
            try:
                result = st.session_state.client.snapshot(st.session_state.session_id)
                if "snapshot" in result:
                    st.session_state.screenshot = result["snapshot"]
                    add_to_history("✓ Screenshot refreshed")
                    st.rerun()
            except Exception as e:
                add_to_history(f"✗ Error: {e}")

        st.divider()

        # Storage state info
        st.header("Storage State")
        if STORAGE_STATE_PATH.exists():
            state = load_storage_state()
            if state:
                n_cookies = len(state.get("cookies", []))
                n_origins = len(state.get("origins", []))
                st.info(f"Cookies: {n_cookies}, Origins: {n_origins}")
        else:
            st.info("No saved state")

    # ==================== Main Area: Two Columns ====================
    col1, col2 = st.columns([2, 1])

    with col1:
        st.subheader("Browser View")

        if st.session_state.screenshot:
            try:
                img = decode_screenshot(st.session_state.screenshot)

                # Apply overlay if we have locate result
                if st.session_state.last_locate:
                    loc = st.session_state.last_locate
                    if loc.get("found"):
                        img = draw_overlay(
                            img,
                            x=loc.get("x"),
                            y=loc.get("y"),
                            confidence=loc.get("confidence"),
                        )

                st.image(img, use_container_width=True)
            except Exception as e:
                st.error(f"Failed to display screenshot: {e}")
        else:
            st.info("No screenshot. Connect and navigate to a URL.")

    with col2:
        st.subheader("Command History")

        # Display history (newest first)
        history_container = st.container(height=400)
        with history_container:
            for entry in reversed(st.session_state.history[-50:]):
                if entry.startswith(">"):
                    st.markdown(f"**{entry}**")
                elif entry.startswith("✓"):
                    st.success(entry)
                elif entry.startswith("✗"):
                    st.error(entry)
                else:
                    st.text(entry)

    # ==================== Command Input ====================
    st.divider()

    prompt_col, button_col = st.columns([4, 1])

    with prompt_col:
        command = st.text_input(
            "Command",
            placeholder='locate "the search button" | click "Submit" | type "input field" hello',
            disabled=not st.session_state.connected,
            key="command_input",
        )

    with button_col:
        st.write("")  # Spacing
        go_clicked = st.button("Go", disabled=not st.session_state.connected)

    if go_clicked and command:
        action, target, extra = parse_command(command)
        add_to_history(f"> {command}")

        try:
            client = st.session_state.client
            session_id = st.session_state.session_id

            if action == "goto":
                result = client.goto(session_id, target)
                if "snapshot" in result:
                    st.session_state.screenshot = result["snapshot"]
                st.session_state.last_locate = None

            elif action == "scroll":
                result = client.scroll(session_id, target)
                if "snapshot" in result:
                    st.session_state.screenshot = result["snapshot"]
                st.session_state.last_locate = None

            elif action == "locate":
                result = client.locate(session_id, target)
                st.session_state.last_locate = result
                if result.get("found"):
                    add_to_history(
                        f"  Found: ({result['x']}, {result['y']}) "
                        f"conf={result.get('confidence', 'N/A')}"
                    )
                else:
                    add_to_history(f"  Not found: {result.get('reasoning', 'unknown')}")

            elif action == "click":
                result = client.click(session_id, target)
                if result.get("success"):
                    add_to_history("  ✓ Clicked")
                    if "snapshot" in result:
                        st.session_state.screenshot = result["snapshot"]
                else:
                    add_to_history(f"  ✗ Click failed: {result.get('error', 'unknown')}")
                st.session_state.last_locate = None

            elif action == "type":
                result = client.type_text(session_id, target, extra)
                if result.get("success"):
                    add_to_history(f"  ✓ Typed: {extra}")
                    if "snapshot" in result:
                        st.session_state.screenshot = result["snapshot"]
                else:
                    add_to_history(f"  ✗ Type failed: {result.get('error', 'unknown')}")
                st.session_state.last_locate = None

            st.rerun()

        except Exception as e:
            add_to_history(f"  ✗ Error: {e}")
            st.rerun()

    # ==================== Help ====================
    with st.expander("Command Help"):
        st.markdown("""
        **Available commands:**

        - `locate "description"` - Find element by description, show coordinates
        - `click "description"` - Click on element
        - `type "description" text` - Type text into element
        - `goto url` - Navigate to URL
        - `scroll up/down` - Scroll the page

        **Examples:**
        ```
        locate "the search button"
        click "Sign in"
        type "email input" user@example.com
        goto https://gemini.google.com
        scroll down
        ```
        """)


if __name__ == "__main__":
    main()
