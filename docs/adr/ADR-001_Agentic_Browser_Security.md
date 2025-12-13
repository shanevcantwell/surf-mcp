# ADR-001: Agentic Browser Security Controls

**Status:** Accepted (Phase 1 Complete)
**Date:** 2025-12-08
**Updated:** 2025-12-13
**Authors:** Shane Cantwell, Claude

---

## Implementation Status

| Phase | Status | Notes |
|-------|--------|-------|
| **Phase 1** | ✅ Complete | Domain filter, audit logging, rate limiting |
| **Phase 1.5** | ⏳ Not started | Squid proxy (Docker infrastructure) |
| **Phase 2** | ⏳ Not started | Sensitive action confirmation, screenshot sanitization |
| **Phase 3** | ⏳ Not started | Behavioral anomaly detection, session recording |

---

## Context

During development of navigator-mcp, we discovered an article published on The Hacker News (December 2025) titled ["Agentic Trojan Horse: Why New AI Browsers Are an Enterprise Nightmare"](https://thehackernews.com/2025/12/webinar-agentic-trojan-horse-why-new-ai.html).

The article identifies critical security concerns with autonomous AI browsers—tools that can independently navigate, interpret UI, input data, and execute transactions without human intervention. This describes exactly what navigator-mcp's BrowserDriver provides via visual grounding.

### Key Threats Identified

1. **The Privilege Paradox**
   Agentic browsers require maximum privileges (session cookies, saved credentials, payment info) to function effectively, directly contradicting least-privilege security principles.

2. **Prompt Injection via DOM**
   Attackers can embed hidden instructions on webpages that the AI interprets and executes within authenticated sessions, bypassing MFA and other controls.

3. **Session Gap**
   Malicious DOM interactions happen locally without revealing intent in network logs, creating a detection blind spot for traditional security monitoring.

4. **Autonomous Action Without Verification**
   The agent can click buttons, submit forms, and initiate transactions without human confirmation—a single compromised visual grounding decision could have significant consequences.

### How This Applies to navigator-mcp

| Threat | navigator-mcp Exposure |
|--------|----------------------|
| Privilege Paradox | BrowserDriver operates with full page context; strategies like `gemini_prompt` require authenticated sessions |
| Prompt Injection | Visual grounding LLM receives raw screenshots; malicious page content could influence `locate()` results |
| Session Gap | Playwright actions are local; no network-level visibility into click/type operations |
| Autonomous Action | `click`, `type`, `scroll` execute immediately without confirmation |

---

## Decision

We will implement a layered security model for navigator-mcp's browser automation capabilities, following the principle of **defense in depth**. The controls are categorized by implementation priority.

### Phase 1: Immediate Controls (v0.1.0)

#### 1.1 URL Allowlist/Blocklist

Add domain-level access control to `BrowserDriver.goto()`:

```python
class BrowserDriver:
    def __init__(
        self,
        allowed_domains: Optional[List[str]] = None,  # Allowlist (if set, only these)
        blocked_domains: Optional[List[str]] = None,  # Blocklist (always denied)
        ...
    ):
        self.allowed_domains = allowed_domains
        self.blocked_domains = blocked_domains or [
            # Default blocklist for sensitive sites
            "*.bank.com", "*.paypal.com", "accounts.google.com",
            "login.microsoftonline.com", "*.stripe.com"
        ]

    async def goto(self, location: str) -> NavigatorState:
        domain = urlparse(location).netloc

        if self._is_blocked(domain):
            return NavigatorState(
                location=await self.current(),
                success=False,
                error=f"Domain blocked by security policy: {domain}"
            )
        ...
```

**Configuration:**
```bash
NAVIGATOR_BROWSER_ALLOWED_DOMAINS=gemini.google.com,chat.openai.com
NAVIGATOR_BROWSER_BLOCKED_DOMAINS=*.bank.com,paypal.com
```

#### 1.2 Comprehensive Audit Logging

Log all visual grounding decisions and browser actions for forensic analysis:

```python
@dataclass
class AuditEvent:
    timestamp: datetime
    session_id: str
    action: str  # "locate", "click", "type", "goto"
    details: Dict[str, Any]
    screenshot_hash: Optional[str]  # SHA256 of screenshot used
    llm_response: Optional[Dict]  # Raw grounding result
    outcome: str  # "success", "failed", "blocked"

class BrowserDriver:
    audit_log: List[AuditEvent] = []

    async def click(self, description: str) -> NavigatorState:
        locate_result = await self.locate(description)

        self._audit(AuditEvent(
            timestamp=datetime.utcnow(),
            session_id=self._session_id,
            action="click",
            details={"description": description, "coordinates": (locate_result.get("x"), locate_result.get("y"))},
            screenshot_hash=self._last_screenshot_hash,
            llm_response=locate_result,
            outcome="attempted"
        ))
        ...
```

#### 1.3 Action Rate Limiting

Prevent runaway automation loops:

```python
class BrowserDriver:
    def __init__(self, max_actions_per_minute: int = 30, ...):
        self.rate_limiter = RateLimiter(max_actions_per_minute)

    async def click(self, description: str) -> NavigatorState:
        if not self.rate_limiter.allow():
            return NavigatorState(
                success=False,
                error="Rate limit exceeded. Too many actions per minute."
            )
        ...
```

### Phase 2: Enhanced Controls (v0.2.0)

#### 2.1 Sensitive Action Confirmation

For high-risk actions, require explicit confirmation or secondary approval:

```python
SENSITIVE_PATTERNS = [
    r"submit|confirm|pay|send|transfer|delete|remove",
    r"password|credential|secret|token",
]

async def click(self, description: str, force: bool = False) -> NavigatorState:
    if self._is_sensitive(description) and not force:
        return NavigatorState(
            success=False,
            error=f"Sensitive action requires confirmation. Use force=True or confirm via callback.",
            metadata={"requires_confirmation": True, "description": description}
        )
```

#### 2.2 Screenshot Sanitization

Before sending screenshots to the visual grounding LLM, apply preprocessing to mitigate prompt injection:

```python
async def _sanitize_screenshot(self, screenshot_b64: str) -> str:
    """
    Preprocess screenshot to reduce prompt injection risk.

    - Detect and blur/redact suspicious text patterns
    - Remove hidden/tiny text (common injection vector)
    - Optionally OCR and filter before LLM sees it
    """
    img = Image.open(io.BytesIO(base64.b64decode(screenshot_b64)))

    # Strategy 1: Detect unusually small text (< 6px) - often used for hidden prompts
    # Strategy 2: Look for known injection patterns via OCR
    # Strategy 3: Hash regions and compare to known-bad patterns

    return sanitized_b64
```

#### 2.3 Visual Grounding Confidence Thresholds

Require minimum confidence for actions:

```python
async def click(self, description: str, min_confidence: float = 0.7) -> NavigatorState:
    locate_result = await self.locate(description)

    if locate_result.get("confidence", 0) < min_confidence:
        return NavigatorState(
            success=False,
            error=f"Confidence {locate_result.get('confidence')} below threshold {min_confidence}",
            metadata={"locate_result": locate_result}
        )
```

### Phase 1.5: Infrastructure-Level Network Control

**Informed by:** [langgraph-agentic-scaffold's Squid proxy implementation](../../../langgraph-agentic-scaffold/proxy/squid.conf)

LAS uses a Squid proxy container to enforce network-level domain whitelisting. This provides **defense in depth** at the infrastructure layer, independent of application-level controls.

#### Squid Proxy Integration

Add a Squid proxy container that all BrowserDriver traffic must route through:

```yaml
# docker-compose.yml
services:
  squid:
    image: ubuntu/squid:latest
    volumes:
      - ./proxy/squid.conf:/etc/squid/squid.conf:ro
    ports:
      - "3128:3128"
    networks:
      - navigator-net

  navigator-mcp:
    build: .
    environment:
      - HTTP_PROXY=http://squid:3128
      - HTTPS_PROXY=http://squid:3128
    depends_on:
      - squid
    networks:
      - navigator-net

networks:
  navigator-net:
    driver: bridge
```

```conf
# proxy/squid.conf - Whitelist configuration
acl SSL_ports port 443
acl Safe_ports port 80
acl Safe_ports port 443
acl Safe_ports port 1234     # LM Studio

# Whitelisted domains for navigator-mcp
acl allowed_domains dstdomain .gemini.google.com    # Gemini Web UI
acl allowed_domains dstdomain .googleapis.com       # Google APIs
acl allowed_domains dstdomain .openai.com           # OpenAI
acl allowed_domains dstdomain host.docker.internal  # LM Studio on host

# Access rules
http_access deny !Safe_ports
http_access deny CONNECT !SSL_ports
http_access allow allowed_domains
http_access deny all  # Strict enforcement

http_port 3128
```

#### Why Squid Proxy?

| Layer | Control | Bypass Difficulty |
|-------|---------|-------------------|
| **Application** | URL allowlist in Python | Easy (code modification) |
| **Network** | Squid proxy whitelist | Hard (requires container escape) |
| **Combined** | Both layers | Very hard |

**Key benefits:**
1. **Audit trail**: Squid logs all HTTP/HTTPS requests with timestamps
2. **Container isolation**: BrowserDriver cannot bypass proxy without escaping container
3. **Centralized policy**: Single squid.conf controls all network access
4. **Familiar tooling**: Standard proxy configuration, widely understood

#### Playwright Proxy Configuration

BrowserDriver must be configured to route through the proxy:

```python
class BrowserDriver:
    async def initialize(self):
        proxy_url = os.environ.get("HTTPS_PROXY")

        context_options = {
            "viewport": {"width": self.viewport[0], "height": self.viewport[1]}
        }

        if proxy_url:
            context_options["proxy"] = {"server": proxy_url}
            logger.info(f"BrowserDriver using proxy: {proxy_url}")

        self._browser = await self._playwright.chromium.launch(headless=self.headless)
        context = await self._browser.new_context(**context_options)
        self._page = await context.new_page()
```

#### Deployment Modes

| Mode | Squid Required | Use Case |
|------|---------------|----------|
| **Docker (default)** | Yes | Production, CI/CD |
| **Standalone** | Optional | Development, testing |

When running standalone without Docker, the application-level URL controls still apply, but without the infrastructure-layer enforcement.

### Phase 3: Advanced Controls (v0.3.0+)

#### 3.1 Behavioral Anomaly Detection

Track normal usage patterns and flag deviations:

```python
class BehaviorMonitor:
    """
    Learns normal patterns per session and flags anomalies:
    - Unusual navigation sequences
    - Actions on unexpected page regions
    - Rapid context switches
    """

    def analyze(self, action: AuditEvent) -> Optional[str]:
        # Returns warning message if anomalous, None if normal
        ...
```

#### 3.2 Content Security Policy for Visual Grounding

Define what the LLM should and shouldn't interact with:

```python
GROUNDING_POLICY = {
    "allowed_element_types": ["button", "input", "link", "textarea"],
    "forbidden_regions": ["header", "footer", "sidebar"],  # By semantic role
    "forbidden_text_patterns": ["admin", "delete all", "confirm payment"],
}
```

#### 3.3 Session Recording and Playback

Record all sessions for audit and incident response:

```python
class SessionRecorder:
    """
    Records complete session for replay:
    - All screenshots (compressed)
    - All actions with timestamps
    - All LLM interactions
    - Network activity (via Playwright)
    """

    async def export(self, session_id: str, format: str = "har") -> bytes:
        ...
```

---

## Consequences

### Positive

- **Reduced attack surface**: URL restrictions prevent navigation to sensitive sites
- **Forensic capability**: Audit logs enable incident investigation
- **Rate limiting**: Prevents runaway automation from causing damage
- **Defense in depth**: Multiple layers mean single bypass isn't catastrophic

### Negative

- **Increased complexity**: More code to maintain and test
- **Performance overhead**: Logging, sanitization, and checks add latency
- **User friction**: Confirmations and restrictions may impede legitimate use cases
- **False positives**: Overly aggressive controls may block valid operations

### Neutral

- **Configuration burden**: Users must configure allowlists for their use cases
- **Storage requirements**: Audit logs and session recordings consume disk space

---

## Implementation Plan

| Phase | Features | Target Version | Effort |
|-------|----------|----------------|--------|
| 1 | URL allowlist/blocklist, Audit logging, Rate limiting | v0.1.0 | 2-3 days |
| 2 | Sensitive action confirmation, Screenshot sanitization, Confidence thresholds | v0.2.0 | 1 week |
| 3 | Behavioral anomaly detection, Content security policy, Session recording | v0.3.0+ | 2+ weeks |

---

## References

1. [Agentic Trojan Horse: Why New AI Browsers Are an Enterprise Nightmare](https://thehackernews.com/2025/12/webinar-agentic-trojan-horse-why-new-ai.html) - The Hacker News, December 2025
2. [OWASP Top 10 for LLM Applications](https://owasp.org/www-project-top-10-for-large-language-model-applications/) - Prompt injection risks
3. [Anthropic's Claude Computer Use Guidelines](https://docs.anthropic.com/en/docs/computer-use) - Safety considerations for autonomous agents

---

## Decision Outcome

**Accepted** - Phase 1 controls will be implemented before initial release. Phase 2 and 3 controls will be prioritized based on deployment context (internal tools vs. external-facing).

The security model follows the principle that **navigator-mcp should fail safe**: when in doubt, deny the action and log the attempt rather than proceed with potentially harmful automation.
