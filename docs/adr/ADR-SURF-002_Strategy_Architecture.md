# ADR-SURF-002: Strategy Architecture

**Status:** Proposed (Stub)
**Date:** 2025-12-10
**Authors:** Shane Cantwell, Claude

---

## Context

Navigator-mcp needs a strategy system to:
1. Provide site-specific guidance to Fara (visual grounding)
2. Handle authentication flows including 2FA
3. Enable reusable navigation patterns
4. Support future learning/adaptation capabilities

This ADR captures the architectural vision without committing to immediate implementation.

---

## Decision

### Strategy Hierarchy

```
BaseStrategy
├── element_hints: Dict[str, str]     # Site-specific Fara guidance
├── auth_config: Optional[AuthConfig] # 2FA/login patterns
├── pre_execute(): Optional setup
├── execute(driver, context) -> StrategyResult
└── post_execute(): Optional cleanup

SiteStrategy (extends BaseStrategy)
├── GeminiStrategy
│   └── element_hints = {"prompt_input": "the text area with 'Enter a prompt'"}
├── ChatGPTStrategy
└── GenericChatbotStrategy

AuthStrategy (extends BaseStrategy)
├── InteractiveAuthStrategy    # Human types credentials
├── StorageStateAuthStrategy   # Load pre-captured cookies
└── MFAStrategy                # Handle 2FA flows

LearnedStrategy (future)
├── RecordedStrategy           # Replay captured sequences
├── AdaptiveStrategy           # Learn from success/failure
└── ElementRecognitionDB       # Site-specific element memory
```

### Authentication Configuration

```python
@dataclass
class AuthConfig:
    """Configuration for authentication flows."""
    login_url: str
    success_indicator: str              # "Dashboard" or visual element
    mfa_type: Optional[str] = None      # "totp", "sms", "push", "interactive"
    mfa_input_hint: Optional[str] = None  # "the 6-digit code input"
    timeout_seconds: int = 120
```

### MFA Handling Patterns

| MFA Type | Handler | Credential Flow |
|----------|---------|-----------------|
| `interactive` | Open non-headless, wait for human | User types directly, navigator-mcp never sees |
| `totp` | `type_from_env(hint, "TOTP_CODE")` | Browser reads env, navigator-mcp orchestrates |
| `push` | `wait_for_element("Approved")` | No credential needed, just wait |
| `sms` | `interactive` or external injection | Depends on setup |

### Element Hints

Site-specific guidance to improve Fara accuracy:

```python
class GeminiStrategy(SiteStrategy):
    element_hints = {
        "prompt_input": "the large text area with placeholder 'Enter a prompt here'",
        "send_button": "the blue arrow button to the right of the text input",
        "response_area": "the assistant's response message bubble",
        "new_chat": "the '+ New chat' button in the sidebar",
    }
```

### Session/Credential Separation (from ADR-SURF-001 discussion)

```
Client Agent (LAS)
├── Owns credential provenance
├── Manages storage_state files
└── Passes context to navigator-mcp

navigator-mcp
├── Ephemeral sessions (default)
├── Loads storage_state if provided
├── Never inspects credential values
└── Forgets everything on cleanup
```

---

## Learned Strategies (Future Vision)

### Recording

```python
class RecordedStrategy:
    """Capture and replay navigation sequences."""

    async def record(self, driver, task_description: str):
        # Track all actions during manual execution
        # Store as reproducible sequence

    async def replay(self, driver, adaptations: dict):
        # Execute recorded sequence
        # Use visual grounding to adapt to UI changes
```

### Feedback Loop

```python
class AdaptiveStrategy:
    """Learn from success/failure patterns."""

    # After each execution:
    # - Record element_hints that worked
    # - Track confidence scores
    # - Build site-specific recognition DB
```

---

## Implementation Priority

| Phase | Features | Target |
|-------|----------|--------|
| **Done** | Direct Fara execution via `act()` | v0.3.0 ✓ |
| **Next** | Basic strategy interface, element_hints | v0.4.0 |
| **Later** | AuthConfig, interactive auth, storage state loading | v0.5.0 |
| **Future** | MFA patterns, learned strategies, recording | v0.6.0+ |

---

## Open Questions

1. **Where do strategies live?** In navigator-mcp or client agent?
   - Proposal: Base classes in navigator-mcp, site-specific in client

2. **How to share element_hints across users?**
   - Could publish as community resource
   - Privacy considerations for learned data

3. **Strategy composition?**
   - Can strategies chain? (Auth -> Navigate -> Extract)
   - Pipeline pattern vs. monolithic execute()

---

## References

- [ADR-SURF-001: Agentic Browser Security](./ADR-SURF-001_Agentic_Browser_Security.md) - Security controls (Phase 1 complete)
- [Playwright Storage State](https://playwright.dev/docs/auth)

## Dependencies

This ADR depends on:
- **ADR-SURF-001 Session/Credential Separation** (implemented): navigator-mcp is stateless; client agents own credentials
- **ADR-SURF-005 Direct Fara Execution** (complete, archived): Fara decides actions via `act()` method

Current implementation provides foundation for strategies via `BrowserDriver.act(goal)` - strategies would provide site-specific guidance to improve Fara accuracy.

---

## Decision Outcome

**Proposed** - This ADR captures architectural direction. The foundation (ADR-SURF-005 direct Fara execution) is now complete in v0.3.0. Strategy interface implementation is planned for v0.4.0.
