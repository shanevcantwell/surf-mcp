# ADR-006: Multi-Screenshot Context for Autonomous Mode

**Status:** Complete
**Date:** 2026-01-06
**Authors:** Shane Cantwell, Claude

---

## Context

Autonomous mode (`act_autonomous`) runs Fara in a loop until task completion. Originally, each step sent only the current screenshot and text-based action history. This worked for simple tasks but caused issues with:

1. **Dropdown toggle traps**: Fara would click a dropdown, then click the same spot again (closing it) instead of selecting an item inside
2. **No visual memory**: Text history like `[1] left_click at (642, 97)` doesn't convey what the UI looked like before/after
3. **Limited reasoning**: Per Fara-7B docs, optimal performance requires "latest screenshots" and "full history of previous thoughts and actions"

---

## Decision

Implement multi-screenshot context for autonomous mode:

1. **StepContext dataclass**: Captures screenshot + action + reasoning per step
2. **`get_action_with_context()` method**: New VisualGrounder method accepting history
3. **OpenAI adapter**: Builds multi-image content array with up to N screenshots
4. **AgentRunner**: Collects StepContext history and passes to grounder
5. **FailoverGrounder**: Delegates `get_action_with_context` to underlying adapter

---

## Implementation

### StepContext (`base.py`)

```python
@dataclass
class StepContext:
    screenshot_b64: str   # Screenshot BEFORE action
    action: str           # e.g., "[1] left_click at (642, 97) ✓"
    reasoning: str = ""   # Fara's chain-of-thought
    success: bool = True  # Whether action succeeded
```

### VisualGrounder Base Method (`base.py`)

```python
async def get_action_with_context(
    self,
    goal: str,
    screenshot_b64: str,
    history: Optional[List[StepContext]] = None,
) -> FaraToolCall:
    # Default: fallback to single-screenshot get_action
    return await self.get_action(goal, screenshot_b64)
```

### OpenAI Adapter (`openai_adapter.py`)

- Builds content array: `[text_prompt, image1, image2, ..., current_image]`
- Includes text history with action summaries and reasoning snippets
- Uses official Fara system prompt from HuggingFace model card
- Scales all images to model's native resolution
- Configurable via `FARA_CONTEXT_SCREENSHOTS` (default: 3)

### AgentRunner (`agent_runner.py`)

```python
def _build_step_contexts(self, steps: List[AgentStep]) -> List[StepContext]:
    # Convert AgentStep records to StepContext for grounder

# In run() loop:
step_contexts = self._build_step_contexts(steps)
if hasattr(self.grounder, "get_action_with_context"):
    tool_call = await self.grounder.get_action_with_context(
        goal, screenshot_b64, history=step_contexts
    )
```

### FailoverGrounder (`factory.py`)

Added `get_action_with_context()` that delegates to underlying adapter with full failover support.

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `FARA_CONTEXT_SCREENSHOTS` | `3` | Max screenshots in context |
| `FARA_SYSTEM_PROMPT` | - | Override system prompt (inline) |
| `FARA_SYSTEM_PROMPT_FILE` | - | Override system prompt (file path) |

---

## Trade-offs

### Pros

- **Better dropdown handling**: Fara can see the menu opened in previous screenshot
- **Visual continuity**: Model understands what changed between actions
- **Follows Fara-7B docs**: Uses recommended multi-screenshot input format
- **Extensible**: System prompt override enables task-specific tuning

### Cons

- **Higher token usage**: ~1K tokens per screenshot at 1280x720
- **Increased latency**: More data to process per request
- **Memory overhead**: Storing screenshots in step history

---

## Verification

Tested via Fara harness:

1. **Navigation task**: "Go to 2027 admissions form on colorado.edu" - Completed in 13 steps
2. **Form filling**: Multi-field forms work with more specific instructions
3. **Token usage**: LM Studio logs show ~3K prompt tokens (3 images) vs ~261 (single image)

---

## Known Limitations

- **Date picker dropdowns**: Multi-dropdown widgets (month/day/year) may still struggle
- **Very long forms**: May exceed step limit (configurable via `FARA_MAX_AGENT_STEPS`)
- **Toggle patterns**: Prompt hints help but don't eliminate all toggle loops

---

## References

- [Fara-7B Model Card](https://huggingface.co/microsoft/Fara-7B) - Multi-screenshot input format
- [ADR-005: Direct Fara Execution](ADR-005_Direct_Fara_Execution.md) - Foundation for autonomous mode
- [OpenAI Vision API](https://platform.openai.com/docs/guides/vision) - Multi-image content format
