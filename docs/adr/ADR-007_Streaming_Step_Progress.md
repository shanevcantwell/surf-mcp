# ADR-007: Streaming Step Progress for Autonomous Execution

**Status:** Proposed (Deferred)
**Date:** 2026-01-06
**Authors:** Shane Cantwell, Claude

---

## Context

`act_autonomous` runs Fara in a loop until task completion (terminate) or max steps. Currently, it returns all results at once after completion:

```python
result = client.act_autonomous(session_id, "search for cats, click first result")
# Returns after all steps complete:
# {"success": True, "step_count": 5, "steps": [...], "final_screenshot": "..."}
```

For long-running tasks (10+ steps), callers have no visibility into progress until completion. This affects:

1. **User Experience**: No feedback during multi-second operations
2. **Cancellation**: Cannot cancel mid-execution based on observed progress
3. **Debugging**: Hard to diagnose which step caused failure

---

## Options Considered

### Option A: MCP Progress Notifications (Server-Side Streaming)

MCP spec supports `notifications/progress` for long-running operations:

```python
# Server sends progress during execution
await ctx.send_progress(progress=3, total=10, message="Step 3: Clicking search button...")
```

**Pros:**
- Standard MCP mechanism
- AgentRunner already has `progress_callback` parameter
- No API change needed

**Cons:**
- MCP SDK support varies by client
- Requires async client handling
- Not all MCP clients implement progress notifications

### Option B: Step-by-Step API (`act_step`)

Expose a new tool that executes one step and returns:

```python
# New tool: act_step
result = client.act_step(session_id, goal, step_state=None)
# Returns: {"step": 1, "action": "left_click", "done": False, "step_state": "..."}

# Caller loops until done
while not result["done"]:
    result = client.act_step(session_id, goal, step_state=result["step_state"])
```

**Pros:**
- Full control at client level
- Natural fit for SSE streaming (LAS pattern)
- Client decides when to stop

**Cons:**
- State must pass through client on every step
- More MCP round-trips
- ReAct history must serialize/deserialize

### Option C: Keep Batch, Enhance Return Data

Keep `act_autonomous` as-is but improve the returned step data:

```python
result = client.act_autonomous(session_id, goal)
# Returns rich step history for post-hoc analysis
```

**Pros:**
- Simplest implementation
- No API changes
- Works today

**Cons:**
- No live progress visibility
- All-or-nothing execution

---

## Decision

**Defer streaming implementation.**

Current `act_autonomous` batch approach is sufficient for:

1. **LAS Integration**: NavigatorBrowserSpecialist calls surf-mcp tools; LAS handles SSE streaming to its UI separately
2. **Fara Harness**: Streamlit UI shows results after completion; step viewer displays history
3. **Typical Tasks**: Most visual grounding tasks complete in <10 steps

### When to Revisit

Implement streaming when:
- LAS testing reveals UX issues with long-running autonomous tasks
- Real-world usage shows tasks commonly exceed 15+ steps
- MCP client ecosystem matures with better progress notification support

### If Implementing Later

Recommended approach: **Option B (act_step)** with the following design:

```python
@mcp.tool()
async def act_step(
    session_id: str,
    goal: str,
    step_state: Optional[str] = None,  # Base64-encoded AgentState
) -> dict:
    """Execute one autonomous step. Caller loops until done=True."""
```

This gives clients full control over streaming UX without requiring MCP progress notifications.

---

## Current Implementation

The infrastructure for streaming exists but is internal:

| Component | Location | Status |
|-----------|----------|--------|
| `AgentRunner.run()` | [agent_runner.py:170](../src/surf_mcp/drivers/agent_runner.py#L170) | Has `progress_callback` parameter |
| `AgentStep` dataclass | [agent_runner.py:28](../src/surf_mcp/drivers/agent_runner.py#L28) | Rich step metadata |
| Step viewer UI | [app.py:279](../tools/fara-harness/app.py#L279) | Post-hoc step navigation |

---

## References

- [ADR-005: Direct Fara Execution](complete/ADR-005_Direct_Fara_Execution.md) - Autonomous mode design
- [MCP Progress Notifications](https://modelcontextprotocol.io/specification/draft/server/utilities/progress)
- [LAS SSE Streaming](../../langgraph-agentic-scaffold/docs/API_REFERENCE.md) - How LAS streams to UI

---

## Dependencies

This ADR depends on:
- **ADR-005 Direct Fara Execution** (complete): Autonomous mode with ReAct history
- **LAS Integration Testing**: Real-world feedback on UX requirements
