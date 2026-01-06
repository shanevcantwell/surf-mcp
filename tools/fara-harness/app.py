"""
Fara Test Harness - Streamlit UI for visual grounding experimentation.

Run with: streamlit run app.py

Per ADR-003: Interactive harness for testing Fara visual grounding
through MCP exclusively (no direct imports from surf-mcp).
"""

import streamlit as st

from mcp_client import SyncSurfClient
from utils import (
    STORAGE_STATE_PATH,
    load_storage_state,
    save_storage_state,
    decode_screenshot,
    draw_overlay,
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
        return "Cannot connect to surf-mcp server. Ensure it is running."

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
    # Multi-step autonomous mode toggle (default: True)
    if "autonomous_mode" not in st.session_state:
        st.session_state.autonomous_mode = True
    # Max steps for autonomous mode
    if "max_steps" not in st.session_state:
        st.session_state.max_steps = 20
    # Step viewer for autonomous mode
    if "step_viewer_index" not in st.session_state:
        st.session_state.step_viewer_index = 0


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
    """
    Execute a command - routes to single-step or autonomous based on mode.
    """
    if not command.strip():
        return

    if st.session_state.autonomous_mode:
        execute_command_autonomous(command)
    else:
        execute_command_single(command)


def execute_command_single(command: str):
    """
    Execute a single-step command via act().

    No parsing, no manipulation. Fara decides what to do.
    """
    add_to_history(f"> {command}")

    try:
        client = st.session_state.client
        session_id = st.session_state.session_id

        # All commands go to Fara - it decides the action
        result = client.act(session_id, command)
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


def execute_command_autonomous(command: str):
    """
    Execute a multi-step command via act_autonomous().

    Fara loops until task complete (terminate) or max steps.
    """
    max_steps = st.session_state.max_steps
    add_to_history(f"🔄 {command} (max {max_steps} steps)")
    add_to_history("  [Autonomous mode - running until complete...]")

    try:
        client = st.session_state.client
        session_id = st.session_state.session_id

        # Multi-step execution with max_steps from UI
        result = client.act_autonomous(session_id, command, max_steps=max_steps)
        st.session_state.last_act_auto = result
        st.session_state.step_viewer_index = 0  # Reset to first step

        step_count = result.get("step_count", 0)
        success = result.get("success", False)
        reason = result.get("reason", "")

        if success:
            add_to_history(f"  ✓ Completed in {step_count} steps")
        else:
            add_to_history(f"  ✗ Failed after {step_count} steps: {reason}")

        # Show step summary
        steps = result.get("steps", [])
        for step in steps[-5:]:  # Show last 5 steps
            action = step.get("action", "unknown")
            add_to_history(f"    Step {step.get('step_number', '?')}: {action}")

        # Auto-refresh screenshot after completion
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
                placeholder = (
                    'goto google.com, search for "olde boston bulldogges", click I\'m Feeling Lucky'
                    if st.session_state.autonomous_mode
                    else 'the search button | click "Sign in" | type "email" user@example.com'
                )
                command = st.text_input(
                    "Command",
                    placeholder=placeholder,
                    label_visibility="collapsed",
                )
            with col_submit:
                submitted = st.form_submit_button("↵", width="stretch")

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

                st.image(img, width="stretch")
            except Exception as e:
                st.error(f"Failed to display screenshot: {e}")
        elif st.session_state.connected:
            st.info("Connected. Enter a URL below or use `goto https://...`")
        else:
            st.info("Click 'Connect' to start a browser session.")

        # ==================== Step Viewer (Autonomous Mode) ====================
        if st.session_state.last_act_auto:
            result = st.session_state.last_act_auto
            steps = result.get("steps", [])

            if steps:
                with st.expander(f"📊 Step Viewer ({len(steps)} steps)", expanded=False):
                    # Navigation
                    col_prev, col_info, col_next = st.columns([1, 3, 1])

                    idx = st.session_state.step_viewer_index
                    idx = max(0, min(idx, len(steps) - 1))

                    with col_prev:
                        if st.button("◀ Prev", disabled=(idx == 0), width="stretch"):
                            st.session_state.step_viewer_index = idx - 1
                            st.rerun()

                    with col_info:
                        step = steps[idx]
                        action = step.get("action", "unknown")
                        success = step.get("success", True)
                        status = "✓" if success else "✗"
                        st.markdown(f"**Step {idx + 1}/{len(steps)}**: `{action}` {status}")

                    with col_next:
                        if st.button("Next ▶", disabled=(idx >= len(steps) - 1), width="stretch"):
                            st.session_state.step_viewer_index = idx + 1
                            st.rerun()

                    # Step details
                    step = steps[idx]
                    coord = step.get("coordinate")
                    text = step.get("text")
                    reasoning = step.get("reasoning", "")

                    details = []
                    if coord:
                        details.append(f"📍 Coordinates: ({coord[0]}, {coord[1]})")
                    if text:
                        details.append(f"📝 Text: `{text}`")
                    if reasoning:
                        details.append(f"💭 Reasoning: {reasoning[:100]}...")

                    if details:
                        st.caption("\n".join(details))

                    # Step screenshot if available
                    screenshot_b64 = step.get("screenshot")
                    if screenshot_b64:
                        try:
                            step_img = decode_screenshot(screenshot_b64)
                            # Draw overlay for click actions
                            if coord and step.get("action") in ("left_click", "click", "type"):
                                step_img = draw_overlay(step_img, x=coord[0], y=coord[1])
                            st.image(step_img, caption=f"Step {idx + 1} screenshot", width="stretch")
                        except Exception as e:
                            st.caption(f"(Screenshot not available: {e})")
                    else:
                        st.caption("(No screenshot for this step)")

    # ==================== Sidebar ====================
    with col_sidebar:
        # Connection controls
        if not st.session_state.connected:
            st.subheader("Connect")
            headless = st.checkbox("Headless mode", value=True)

            if st.button("Connect", width="stretch"):
                try:
                    client = SyncSurfClient()
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
            # Navigation (direct MCP calls - not through Fara)
            st.subheader("Navigate")
            with st.form(key="nav_form", clear_on_submit=False):
                url = st.text_input("URL", value=DEFAULT_URL, label_visibility="collapsed")
                if st.form_submit_button("Go", width="stretch"):
                    try:
                        result = st.session_state.client.goto(
                            st.session_state.session_id, url
                        )
                        if result.get("error"):
                            add_to_history(f"  ✗ {result['error']}")
                        else:
                            add_to_history(f"  ✓ Navigated to {url}")
                        refresh_screenshot()
                    except Exception as e:
                        add_to_history(f"  ✗ Error: {e}")
                    st.rerun()

            # Autonomous mode controls
            st.session_state.autonomous_mode = st.checkbox(
                "🔄 Autonomous",
                value=st.session_state.autonomous_mode,
                help="Multi-step execution until task complete",
            )
            if st.session_state.autonomous_mode:
                st.session_state.max_steps = st.number_input(
                    "Max steps",
                    min_value=1,
                    max_value=100,
                    value=st.session_state.max_steps,
                    help="Maximum steps before giving up",
                )

            # Quick actions (direct MCP calls)
            col1, col2 = st.columns(2)
            with col1:
                if st.button("↑", width="stretch", help="Scroll up"):
                    try:
                        st.session_state.client.scroll(st.session_state.session_id, "up")
                        add_to_history("  ✓ Scrolled up")
                        refresh_screenshot()
                    except Exception as e:
                        add_to_history(f"  ✗ Error: {e}")
                    st.rerun()
            with col2:
                if st.button("↓", width="stretch", help="Scroll down"):
                    try:
                        st.session_state.client.scroll(st.session_state.session_id, "down")
                        add_to_history("  ✓ Scrolled down")
                        refresh_screenshot()
                    except Exception as e:
                        add_to_history(f"  ✗ Error: {e}")
                    st.rerun()

            if st.button("🔄 Refresh", width="stretch"):
                refresh_screenshot()
                add_to_history("✓ Screenshot refreshed")
                st.rerun()

            st.divider()

            # Disconnect
            if st.button("Disconnect", width="stretch", type="secondary"):
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
- `Go to https://example.com`

**Tips:**
- Be specific: "the blue Submit button" > "submit"
- Use visual cues: "the hamburger menu in the top right"
- For dropdowns covering buttons: "press enter" or "press escape"
- Use the sidebar URL field for direct navigation
        """)


if __name__ == "__main__":
    main()
