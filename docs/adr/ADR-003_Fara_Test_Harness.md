# ADR-003: Fara Visual Grounding Test Harness

**Status:** Proposed
**Date:** 2025-12-10
**Authors:** Shane Cantwell, Claude

---

## Context

Before designing complex strategy systems (ADR-002), we need hands-on experience with Fara-7b's visual grounding capabilities. A test harness will let us:

1. Experiment with different prompt formulations
2. Understand Fara's coordinate accuracy and failure modes
3. Test against various web UIs (Gemini, ChatGPT, etc.)
4. Build intuition before abstracting patterns

---

## Decision

Build a **Fara Test Harness** - a local GUI application for interactive visual grounding experimentation.

### UI Layout

```
┌────────────────────────────────────────────────────────────────────────┐
│  Fara Test Harness                                            [─][□][×]│
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌─────────────────────────────────────────┐ ┌──────────────────────┐ │
│  │                                         │ │ Chat History (67%)   │ │
│  │                                         │ │ ─────────────────    │ │
│  │         Browser Frame                   │ │                      │ │
│  │         (Live Playwright view)          │ │ > locate "submit"    │ │
│  │                                         │ │ Found: (450, 320)    │ │
│  │         • Click highlights element      │ │ Conf: 0.92           │ │
│  │         • Red dot shows coordinates     │ │                      │ │
│  │                                         │ │ > locate "the blue   │ │
│  │                                         │ │   login button"      │ │
│  │                                         │ │ Found: (200, 150)    │ │
│  │                                         │ │ Conf: 0.87           │ │
│  │                                         │ │                      │ │
│  │                                         │ │ > click "send"       │ │
│  │                                         │ │ Clicked: (500, 400)  │ │
│  │                                         │ │                      │ │
│  └─────────────────────────────────────────┘ │ [scrollable]         │ │
│                                              └──────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────────────┐│
│  │ Prompt: [locate "the prompt input area"                    ] [Go] ││
│  └───────────────────────────────────────────────────────────────────┘│
│                                                                        │
│  URL: [https://gemini.google.com________________________] [Navigate]   │
│  Status: Connected to LM Studio (Fara-7b) | Viewport: 1920x1080       │
└────────────────────────────────────────────────────────────────────────┘
```

### Features

| Feature | Description |
|---------|-------------|
| **Live Browser** | Playwright-controlled Chromium, non-headless |
| **Prompt Input** | Send locate/click/type commands to Fara |
| **Chat History** | Scrollable log of all commands and Fara responses |
| **Visual Overlay** | Red dot on screenshot showing detected coordinates |
| **Confidence Display** | Show Fara's confidence score for each locate |
| **Screenshot Capture** | Save current screenshot + Fara response for analysis |
| **URL Navigation** | Direct URL input for testing different sites |

### Commands

```
locate "description"     → Returns coordinates, shows overlay
click "description"      → Locates then clicks
type "description" text  → Locates, clicks, types
screenshot               → Save current screenshot
compare "desc1" "desc2"  → Compare two locate results
```

### Implementation Options

| Option | Technology | Pros | Cons |
|--------|------------|------|------|
| **A** | Tkinter + Playwright | Pure Python, no deps | Limited browser embedding |
| **B** | PyQt + QWebEngine | Native feel, good embedding | Heavier deps |
| **C** | Streamlit | Rapid dev, web-based | Less native, refresh-based |
| **D** | Electron + Python backend | Best UX | Two languages |

**Recommendation:** Start with **Streamlit** for rapid iteration, migrate to PyQt if needed.

### Streamlit Sketch

```python
import streamlit as st
from navigator_mcp.drivers.browser import BrowserDriver
from navigator_mcp.llm import OpenAIVisualGrounder

st.set_page_config(layout="wide")

# Sidebar: URL and controls
with st.sidebar:
    url = st.text_input("URL", "https://gemini.google.com")
    if st.button("Navigate"):
        st.session_state.driver.goto(url)

# Main: Two columns
col1, col2 = st.columns([2, 1])

with col1:
    # Display current screenshot with overlay
    if "screenshot" in st.session_state:
        st.image(st.session_state.screenshot)

with col2:
    # Chat history
    for msg in st.session_state.get("history", []):
        st.text(msg)

# Prompt input
prompt = st.text_input("Prompt", key="prompt")
if st.button("Go") and prompt:
    result = await st.session_state.driver.locate(prompt)
    st.session_state.history.append(f"> {prompt}")
    st.session_state.history.append(f"  {result}")
```

---

## Test Scenarios

### Basic Grounding
- [ ] Locate buttons by color ("the blue button")
- [ ] Locate inputs by placeholder text
- [ ] Locate elements by position ("top right corner")
- [ ] Locate elements by content ("the message that says 'Hello'")

### Edge Cases
- [ ] Multiple similar elements (which "Submit" button?)
- [ ] Elements off-screen (needs scroll)
- [ ] Dynamic content (loading spinners)
- [ ] Overlays/modals
- [ ] Dark mode vs light mode

### Site-Specific
- [ ] Gemini chat interface
- [ ] ChatGPT interface
- [ ] Google search
- [ ] Generic forms

---

## Success Criteria

1. Can interactively send prompts to Fara and see results
2. Visual feedback shows where Fara thinks elements are
3. Can iterate on prompt wording quickly
4. Can save successful patterns for strategy development

---

## Implementation Plan

| Phase | Scope | Effort |
|-------|-------|--------|
| **1** | Basic Streamlit harness with screenshot + prompt | 1 day |
| **2** | Live browser control, click/type | 1 day |
| **3** | Overlay visualization, history export | 1 day |

---

## Open Questions

1. **LM Studio connection:** Assume running on `localhost:1234`?
2. **Auth for target sites:** Use storage_state loading?
3. **Recording:** Save sessions for replay/analysis?

---

## References

- [Fara-7b on Hugging Face](https://huggingface.co/gao-zijian/fara-7b)
- [Streamlit Documentation](https://docs.streamlit.io/)
- [ADR-002: Strategy Architecture](./ADR-002_Strategy_Architecture.md)

---

## Decision Outcome

**Proposed** - Build this before diving deeper into strategy patterns. Hands-on experience with Fara will inform better abstractions.
