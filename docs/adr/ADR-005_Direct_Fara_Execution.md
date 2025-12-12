# ADR-005: Direct Fara Execution Architecture

**Status:** Accepted
**Date:** 2025-12-11
**Authors:** Shane Cantwell, Claude

---

## Context

### The Problem

Navigator-mcp's current visual grounding architecture is **convoluted**. We use Fara-7B (an agentic vision model) but treat it as a simple coordinate extractor:

```
Current Flow (Convoluted):
┌─────────────────────────────────────────────────────────────────────────┐
│ User: "click the search button"                                         │
│                                                                         │
│  1. BrowserDriver.click(description)                                    │
│  2. → locate(description)                                               │
│  3. → Fara API call with screenshot                                     │
│  4. → Fara returns: {"name": "computer_use",                            │
│                      "arguments": {"action": "left_click",              │
│                                    "coordinate": [624, 280]}}           │
│  5. → _normalize_tool_call() extracts x=624, y=280  ← DISCARDS action   │
│  6. → Returns LocateResult{found=True, x=624, y=280}                    │
│  7. → BrowserDriver.click() calls page.mouse.click(624, 280) ← RE-IMPLEMENTS │
└─────────────────────────────────────────────────────────────────────────┘
```

**We're working around Fara's output instead of using it directly.**

Fara is designed as an **agent** that decides *what action to take*. Its output includes:
- `left_click` / `click` / `double_click`
- `type` with text
- `scroll` with direction/pixels
- `key` with key names
- `visit_url` with URL
- `terminate` when task complete

But we throw away the action and re-implement it ourselves.

### Key Question: Is Playwright Sufficient?

**Yes** - Playwright is a complete browser automation framework:
- Navigate, click, type, scroll, screenshot
- Handle popups, iframes, file downloads
- Wait for elements, network, animations
- Session management, cookies, localStorage

**What Fara adds**: Natural language element finding ("the blue submit button") instead of brittle CSS selectors.

### Current Pain Points

1. **Duplicate logic**: BrowserDriver has `click()`, `type()`, `scroll()` methods that re-implement what Fara already decided
2. **Lost context**: Fara's reasoning about *why* it chose an action is discarded
3. **Inflexible**: Can't easily add new Fara actions without modifying BrowserDriver
4. **Confusing code**: Developers must understand both Fara's output format AND BrowserDriver's methods

---

## Decision

Refactor to **direct execution**: Fara's tool_call output flows directly to a PlaywrightExecutor.

```
Proposed Flow (Direct):
┌─────────────────────────────────────────────────────────────────────────┐
│ User: "click the search button"                                         │
│                                                                         │
│  1. BrowserDriver.act(goal)                                             │
│  2. → grounder.get_action(goal, screenshot)                             │
│  3. → Fara API call                                                     │
│  4. → Returns FaraToolCall{action="left_click", coordinate=(624, 280)}  │
│  5. → PlaywrightExecutor.execute(tool_call, page)                       │
│  6. → Executes page.mouse.click(624, 280)                               │
└─────────────────────────────────────────────────────────────────────────┘
```

### Architecture Diagram

```
┌────────────────────────────────────────────────────────────────────────────┐
│                          navigator-mcp Architecture                        │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  ┌─────────────┐    goal     ┌──────────────────┐                         │
│  │   MCP Tool  │ ──────────► │   BrowserDriver  │                         │
│  │   (click,   │             │                  │                         │
│  │    type,    │             │   act(goal)      │                         │
│  │    scroll)  │             └────────┬─────────┘                         │
│  └─────────────┘                      │                                   │
│                                       │ screenshot + goal                 │
│                                       ▼                                   │
│                          ┌────────────────────────┐                       │
│                          │   VisualGrounder       │                       │
│                          │   (OpenAI/Gemini)      │                       │
│                          │                        │                       │
│                          │   get_action() ──────► │ LM Studio / API       │
│                          └────────────┬───────────┘                       │
│                                       │                                   │
│                                       │ FaraToolCall                      │
│                                       ▼                                   │
│                          ┌────────────────────────┐                       │
│                          │  PlaywrightExecutor    │                       │
│                          │                        │                       │
│                          │   execute(tool_call)   │                       │
│                          │   ├─ left_click        │                       │
│                          │   ├─ type              │                       │
│                          │   ├─ scroll            │                       │
│                          │   ├─ key               │                       │
│                          │   ├─ visit_url         │                       │
│                          │   └─ terminate         │                       │
│                          └────────────┬───────────┘                       │
│                                       │                                   │
│                                       ▼                                   │
│                          ┌────────────────────────┐                       │
│                          │      Playwright        │                       │
│                          │        Page            │                       │
│                          └────────────────────────┘                       │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### New Data Model: FaraToolCall

```python
@dataclass
class FaraToolCall:
    """
    Represents a complete Fara tool_call, preserving all action details.

    Unlike LocateResult (coordinates only), this captures Fara's full decision.
    """
    action: str  # "left_click", "type", "scroll", "key", "visit_url", "terminate"
    coordinate: Optional[Tuple[int, int]] = None
    text: Optional[str] = None       # For type action
    direction: Optional[str] = None  # For scroll: "up" or "down"
    pixels: Optional[int] = None     # For scroll amount
    url: Optional[str] = None        # For visit_url
    keys: Optional[List[str]] = None # For key action: ["Enter"], ["Control", "c"]
    confidence: float = 1.0
    reasoning: str = ""              # Fara's chain-of-thought
```

### New Component: PlaywrightExecutor

```python
class PlaywrightExecutor:
    """
    Execute Fara tool_calls directly against Playwright.

    This is a thin translation layer - Fara decides what to do,
    we just execute it.
    """

    async def execute(self, tool_call: FaraToolCall, page: Page) -> ExecutionResult:
        """Execute a single Fara tool_call."""
        match tool_call.action:
            case "left_click" | "click":
                await page.mouse.click(*tool_call.coordinate)

            case "double_click":
                await page.mouse.dblclick(*tool_call.coordinate)

            case "type":
                if tool_call.coordinate:
                    await page.mouse.click(*tool_call.coordinate)
                await page.keyboard.type(tool_call.text, delay=50)

            case "scroll":
                pixels = tool_call.pixels or 500
                delta = pixels if tool_call.direction == "down" else -pixels
                await page.mouse.wheel(0, delta)

            case "key":
                for key in tool_call.keys or []:
                    await page.keyboard.press(key)

            case "visit_url":
                await page.goto(tool_call.url, wait_until="networkidle")

            case "terminate":
                pass  # Task complete signal

            case _:
                raise UnsupportedActionError(
                    f"Fara returned unsupported action '{tool_call.action}'. "
                    f"Supported: left_click, type, scroll, key, visit_url, terminate"
                )

        return ExecutionResult(success=True, action=tool_call.action)
```

### Agent Mode with MCP Streaming

For autonomous multi-step tasks, agent mode loops until Fara returns `terminate`:

**MCP Progress Notifications** ([spec](https://modelcontextprotocol.io/specification/2025-03-26/basic/utilities/progress/)):
- Server sends `notifications/progress` with `progressToken`, `progress`, `total`, `message`
- Enables real-time streaming of each Fara step to client

**MCP Cancellation** ([spec](https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/cancellation)):
- Client sends `notifications/cancelled` with `requestId` and optional `reason`
- Server checks cancellation flag between autonomous steps

### Confidence-Based Retry

Low-confidence results trigger retry with different random seeds:

```python
async def get_action_with_retry(self, goal: str, screenshot: str) -> FaraToolCall:
    """Get action from Fara, retrying with new seed if low confidence."""
    min_conf = float(os.environ.get("FARA_MIN_CONFIDENCE", "0.7"))
    max_retries = int(os.environ.get("FARA_CONFIDENCE_RETRIES", "2"))

    best_result = None
    for attempt in range(max_retries + 1):
        result = await self._invoke_fara(goal, screenshot, seed=attempt)

        if result.confidence >= min_conf:
            return result

        if best_result is None or result.confidence > best_result.confidence:
            best_result = result

    return best_result  # Return best attempt even if below threshold
```

---

## Configuration

New environment variables:

```bash
# Confidence threshold (0.0-1.0). Below this, retry with new seed.
FARA_MIN_CONFIDENCE=0.7

# Max retries when confidence below threshold
FARA_CONFIDENCE_RETRIES=2

# Max steps in agent mode before giving up
FARA_MAX_AGENT_STEPS=20
```

---

## Files Modified

| File | Change |
|------|--------|
| `src/navigator_mcp/llm/base.py` | Add `FaraToolCall` dataclass, `UnsupportedActionError` |
| `src/navigator_mcp/llm/openai_adapter.py` | Add `get_action()`, `get_action_with_retry()` |
| `src/navigator_mcp/drivers/playwright_executor.py` | **New** - Action execution |
| `src/navigator_mcp/drivers/agent_runner.py` | **New** - Agent mode with progress/cancel |
| `src/navigator_mcp/drivers/browser.py` | Add `act()` method, integrate executor |

---

## Migration Strategy

**Phase 1**: Add new code alongside old (FaraToolCall, PlaywrightExecutor, get_action)
**Phase 2**: Wire up new flow (act() uses executor, click/type/scroll delegate)
**Phase 3**: Deprecate LocateResult
**Phase 4**: Remove deprecated code (future version)

---

## Consequences

### Positive

- **Cleaner mental model**: Goal → Fara → Action → Result
- **Fara as true agent**: It decides what action, we just execute
- **Extensible**: New Fara actions only need executor changes
- **Better debugging**: Full tool_call visible in logs/harness
- **Future-ready**: Same executor works with other vision models

### Negative

- **Migration effort**: Existing tests and code need updates
- **Two code paths temporarily**: During migration, both old and new flows exist

### Neutral

- **MCP API unchanged**: External clients don't see the difference
- **Same security controls**: Rate limiting, audit logging still apply

---

## References

- [ADR-001: Agentic Browser Security](./ADR-001_Agentic_Browser_Security.md)
- [ADR-003: Fara Test Harness](./ADR-003_Fara_Test_Harness.md)
- [Fara-7B on Hugging Face](https://huggingface.co/gao-zijian/fara-7b)
- [Playwright Documentation](https://playwright.dev/python/docs/api/class-page)
- [MCP Progress Notifications](https://modelcontextprotocol.io/specification/2025-03-26/basic/utilities/progress/)
- [MCP Cancellation](https://modelcontextprotocol.io/specification/2025-06-18/basic/utilities/cancellation)
