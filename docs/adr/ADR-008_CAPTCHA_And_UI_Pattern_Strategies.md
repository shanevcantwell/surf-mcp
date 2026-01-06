# ADR-008: CAPTCHA and UI Pattern Strategies

**Status:** Proposed
**Date:** 2026-01-06
**Authors:** Shane Cantwell, Claude

---

## Context

Visual browser automation faces inherent challenges with certain UI patterns and bot detection mechanisms:

### CAPTCHA and Bot Detection

Modern bot detection systems (Cloudflare Turnstile, reCAPTCHA, FCaptcha, Bing verification) analyze behavioral patterns beyond just screenshots:

1. **Mouse movement analysis**: CAPTCHAs track cursor motion paths. Playwright's `page.mouse.click(x, y)` teleports the cursor instantly - no realistic acceleration, curves, or micro-corrections.

2. **Browser fingerprinting**: Detection scripts identify headless browsers via navigator properties, WebGL rendering, audio context, and timing signatures.

3. **Behavioral signals**: Time between page load and interaction, scroll patterns, keyboard timing - all feed into bot detection models.

4. **Vision AI targeting**: Modern CAPTCHAs specifically target screenshot-to-API workflows used by vision models.

### Problematic UI Patterns

Certain UI patterns cause loops or failures in autonomous mode:

1. **Dropdown toggles**: Clicking a dropdown opens it, but clicking the same spot again closes it instead of selecting an item.

2. **Date pickers**: Multi-dropdown month/day/year selectors require precise sequential interaction.

3. **Modal overlays**: Pop-ups and cookie banners obscure the target elements.

4. **Infinite scroll**: Content loads dynamically, requiring scroll-then-wait patterns.

5. **Two-phase buttons**: Buttons that change state after first click (confirm dialogs, loading states).

---

## Potential Strategies

### CAPTCHA Mitigation

| Strategy | Complexity | Effectiveness | Notes |
|----------|------------|---------------|-------|
| **Realistic mouse paths** | Medium | Low-Medium | Generate bezier curves with noise between points. Still detectable via timing/acceleration analysis. |
| **Human cursor simulation** | High | Medium | Record and replay human mouse movements. Requires substantial recording dataset. |
| **Browser fingerprint hardening** | Medium | Medium | Use puppeteer-extra-plugin-stealth patterns. Cat-and-mouse with detection services. |
| **CAPTCHA solver integration** | Low | High | Integrate 2Captcha, Anti-Captcha, or similar services. Adds cost and external dependency. |
| **User prompt for CAPTCHA** | Low | High | Detect CAPTCHA, pause automation, prompt user to solve manually, then resume. Clean separation of concerns. |
| **Pre-authenticated sessions** | Low | High | Use storage_state from manual login. Avoids CAPTCHA by starting from authenticated state. |

**Recommendation:** Start with pre-authenticated sessions (storage_state) and user prompting for CAPTCHA detection. These require minimal code and respect the fundamental limitation.

### UI Pattern Handling

| Pattern | Strategy |
|---------|----------|
| **Dropdown toggles** | Multi-screenshot context (ADR-006) helps. Prompt engineering: "Select from the dropdown menu that is now open" |
| **Date pickers** | Break into explicit steps: "Click the month dropdown, select January, click the day dropdown, select 15" |
| **Modal overlays** | Add `dismiss_overlay` action that looks for common close patterns (X button, "Accept" button, click-outside) |
| **Infinite scroll** | Add `scroll_and_wait` action that scrolls then waits for network idle |
| **Two-phase buttons** | Multi-screenshot context helps. Alternative: add action retry with state change detection |

---

## Detection Heuristics

Future work could add heuristics to detect and handle these patterns:

### Timeout Heuristic (Observed)

**Key insight**: CAPTCHA pages manifest as `networkidle` timeouts.

When `visit_url` uses `wait_until="networkidle"`, CAPTCHA pages never reach idle because:
1. JavaScript continuously polls for behavioral signals
2. Bot detection scripts maintain persistent connections
3. The page waits indefinitely for human interaction

This pattern was observed in practice:
```
Action 'visit_url' failed: Page.goto: Timeout 30000ms exceeded.
  - navigating to "https://www.bing.com/search?q=...", waiting until "networkidle"
```

**Heuristic**: `visit_url` timeout to known search engines (google.com, bing.com, duckduckgo.com) + networkidle failure = probable CAPTCHA.

**Potential response**:
- Log warning about likely CAPTCHA
- Capture screenshot for user review
- Suggest using storage_state from manual session
- Or integrate with CAPTCHA solver service

### Screenshot-Based Detection

```python
# Pseudocode for CAPTCHA detection
async def detect_captcha(screenshot_b64: str) -> bool:
    """Detect common CAPTCHA patterns in screenshot."""
    # OCR for "verify you are human", "I'm not a robot", etc.
    # Image recognition for checkbox CAPTCHA widgets
    # URL pattern matching (/challenge/, /captcha/, etc.)
    pass

# Pseudocode for dropdown state detection
async def is_dropdown_open(prev_screenshot: str, curr_screenshot: str) -> bool:
    """Detect if a dropdown menu opened between screenshots."""
    # Image diff to detect new overlay/menu appearing
    # Check for expanded area in comparison
    pass
```

---

## Implementation Priority

1. **Document limitations** (Done in README) - Users need to know what doesn't work
2. **Storage state guidance** - Best practice documentation for pre-authenticated sessions
3. **CAPTCHA detection + pause** - Low effort, high value for user experience
4. **UI pattern prompt templates** - Guidance for breaking down complex interactions
5. **Mouse path simulation** - Only if demand justifies complexity

---

## Decision

**Defer implementation** until real-world usage patterns emerge. Current mitigations:

1. Document CAPTCHA as a known limitation
2. Recommend storage_state for authenticated sessions
3. Multi-screenshot context (ADR-006) helps with dropdown issues
4. Prompt engineering guidance in README

Future work should be driven by actual user needs rather than anticipated problems.

---

## References

- [Playwright Stealth](https://github.com/nickreese/playwright-stealth) - Browser fingerprint hardening
- [2Captcha API](https://2captcha.com/2captcha-api) - CAPTCHA solving service
- [ADR-006: Multi-Screenshot Context](complete/ADR-006_Multi_Screenshot_Context.md) - Visual memory for UI state
- [Cloudflare Bot Management](https://www.cloudflare.com/products/bot-management/) - Detection techniques
