"""
Fara Test Harness - Streamlit UI for visual grounding experimentation.

Run with: streamlit run app.py

Per ADR-003: Interactive harness for testing Fara visual grounding
through MCP exclusively (no direct imports from navigator-mcp).
"""

import streamlit as st

from mcp_client import SyncNavigatorClient
from utils import (
    STORAGE_STATE_PATH,
    load_storage_state,
    save_storage_state,
    decode_screenshot,
    draw_overlay,
    parse_command,
)


DEFAULT_URL = "https://www.google.com"


# ==================== Error Handling ====================

def format_error(error: str) -> str:
    """Format error message for display, extracting key information."""
    if "Playwright browser not installed" in error or "Executable doesn't exist" in error:
        return "Playwright browser not installed. Run: `playwright install chromium`"

    if "browser has been closed" in error or "Target page, context" in error:
        return (
            "Browser closed unexpectedly. If running in WSL without a display:\n"
            "1. Install an X server (VcXsrv, X410) on Windows\n"
            "2. Set DISPLAY=:0 in your shell\n"
            "3. Or run with headless=True in session_create"
        )

    if "Connection refused" in error:
        return "Cannot connect to navigator-mcp server. Ensure it is running."

    if "playwright package required" in error.lower():
        return "Playwright not installed. Run: `pip install playwright && playwright install chromium`"

    return error


def show_error(error: str) -> None:
    """Display error in a scrollable container."""
    formatted = format_error(error)
    st.error(formatted)


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
    # ADR-005: Track last act result for tool_call display
    if "last_act" not in st.session_state:
        st.session_state.last_act = None
    if "last_act_auto" not in st.session_state:
        st.session_state.last_act_auto = None


def add_to_history(entry: str):
    """Add entry to chat history."""
    st.session_state.history.append(entry)
    if len(st.session_state.history) > 100:
        st.session_state.history = st.session_state.history[-100:]


def refresh_screenshot():
    """Refresh the screenshot from browser."""
    if st.session_state.connected and st.session_state.client:
        try:
            result = st.session_state.client.snapshot(st.session_state.session_id)
            if "snapshot" in result:
                st.session_state.screenshot = result["snapshot"]
        except Exception:
            pass  # Silent fail on auto-refresh


def execute_command(command: str):
    """Execute a command and update state."""
    if not command.strip():
        return

    action, target, extra = parse_command(command)
    add_to_history(f"> {command}")

    try:
        client = st.session_state.client
        session_id = st.session_state.session_id

        if action == "goto":
            # Direct navigation - no LLM needed
            result = client.goto(session_id, target)
            if "error" in result:
                add_to_history(f"  ✗ {result['error']}")
            else:
                add_to_history(f"  ✓ Navigated to {target}")

        elif action == "scroll":
            # Simple scroll - no LLM needed
            result = client.scroll(session_id, target)
            add_to_history(f"  ✓ Scrolled {target}")

        elif action == "act":
            # Everything else: let Fara decide what to do
            result = client.act(session_id, target)
            st.session_state.last_act = result

            # Extract action info from result
            fara_action = result.get("fara_action", "unknown")
            coord = result.get("coordinate")
            reasoning = result.get("reasoning", "")

            if result.get("success"):
                if coord:
                    add_to_history(f"  ✓ {fara_action} at ({coord[0]}, {coord[1]})")
                else:
                    add_to_history(f"  ✓ {fara_action}")
                if reasoning:
                    add_to_history(f"    {reasoning[:80]}...")
            else:
                error = result.get("error", "unknown")
                add_to_history(f"  ✗ {error}")

        # Auto-refresh screenshot after action
        refresh_screenshot()

    except Exception as e:
        add_to_history(f"  ✗ Error: {e}")


# ==================== Main UI ====================

def main():
    st.set_page_config(
        page_title="Fara Test Harness",
        page_icon="🎯",
        layout="wide",
    )

    init_session_state()

    # ==================== Header with Connection Status ====================
    col_title, col_status = st.columns([3, 1])
    with col_title:
        st.title("🎯 Fara Test Harness")
    with col_status:
        if st.session_state.connected:
            st.success(f"🟢 Connected")
        else:
            st.warning("🔴 Disconnected")

    # ==================== Command Input (Top - Enter submits) ====================
    if st.session_state.connected:
        with st.form(key="command_form", clear_on_submit=True):
            col_input, col_submit = st.columns([5, 1])
            with col_input:
                command = st.text_input(
                    "Command",
                    placeholder='the search button | click "Sign in" | type "email" user@example.com',
                    label_visibility="collapsed",
                )
            with col_submit:
                submitted = st.form_submit_button("↵", use_container_width=True)

            if submitted and command:
                execute_command(command)
                st.rerun()

    # ==================== Main Layout ====================
    col_browser, col_sidebar = st.columns([3, 1])

    # ==================== Browser View ====================
    with col_browser:
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
        elif st.session_state.connected:
            st.info("Connected. Enter a URL below or use `goto https://...`")
        else:
            st.info("Click 'Connect' to start a browser session.")

    # ==================== Sidebar ====================
    with col_sidebar:
        # Connection controls
        if not st.session_state.connected:
            st.subheader("Connect")
            headless = st.checkbox("Headless mode", value=True)

            if st.button("Connect", use_container_width=True):
                try:
                    client = SyncNavigatorClient()
                    client.connect()

                    storage_state = load_storage_state()
                    result = client.session_create(
                        headless=headless,
                        storage_state=storage_state,
                    )

                    if "error" in result:
                        show_error(result['error'])
                    else:
                        st.session_state.client = client
                        st.session_state.session_id = result["session_id"]
                        st.session_state.connected = True
                        add_to_history(f"✓ Connected: {result['session_id'][:8]}...")
                        st.rerun()

                except Exception as e:
                    show_error(str(e))
        else:
            # Navigation
            st.subheader("Navigate")
            with st.form(key="nav_form", clear_on_submit=False):
                url = st.text_input("URL", value=DEFAULT_URL, label_visibility="collapsed")
                if st.form_submit_button("Go", use_container_width=True):
                    execute_command(f"goto {url}")
                    st.rerun()

            # Quick actions
            col1, col2 = st.columns(2)
            with col1:
                if st.button("↑", use_container_width=True, help="Scroll up"):
                    execute_command("scroll up")
                    st.rerun()
            with col2:
                if st.button("↓", use_container_width=True, help="Scroll down"):
                    execute_command("scroll down")
                    st.rerun()

            if st.button("🔄 Refresh", use_container_width=True):
                refresh_screenshot()
                add_to_history("✓ Screenshot refreshed")
                st.rerun()

            st.divider()

            # Disconnect
            if st.button("Disconnect", use_container_width=True, type="secondary"):
                try:
                    result = st.session_state.client.session_destroy(
                        st.session_state.session_id
                    )
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

        # History
        st.divider()
        st.subheader("History")
        history_container = st.container(height=300)
        with history_container:
            for entry in reversed(st.session_state.history[-30:]):
                if entry.startswith(">"):
                    st.code(entry[2:], language=None)
                elif "✓" in entry:
                    st.caption(f"🟢 {entry.replace('✓', '').strip()}")
                elif "✗" in entry:
                    st.caption(f"🔴 {entry.replace('✗', '').strip()}")
                else:
                    st.caption(entry)

    # ==================== Help (collapsed by default) ====================
    with st.expander("Command Help"):
        st.markdown("""
**Just type what you want to do** - Fara understands natural language:

- `Click the search button`
- `Type hello into the search box`
- `Press enter`
- `Find the login link`
- `Scroll down`

**Navigation:**
- `goto https://example.com`
- `scroll up` / `scroll down`

**Tips:**
- Be specific: "the blue Submit button" > "submit"
- Use visual cues: "the hamburger menu in the top right"
- For dropdowns covering buttons: "press enter" or "press escape"
        """)


if __name__ == "__main__":
    main()
