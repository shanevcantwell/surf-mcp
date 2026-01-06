"""
AgentRunner - Autonomous Fara execution with progress streaming.

Per ADR-005: Runs Fara in an autonomous loop until the task is complete
(terminate action) or cancelled. Supports MCP progress notifications
and cancellation.

MCP Integration:
- Progress: Sends notifications/progress with progressToken
- Cancellation: Checks cancelled flag between steps
"""

import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, List, Optional

from ..llm.base import ExecutionResult, FaraToolCall

if TYPE_CHECKING:
    from playwright.async_api import Page
    from ..llm.base import VisualGrounder
    from .playwright_executor import PlaywrightExecutor

logger = logging.getLogger(__name__)


@dataclass
class AgentStep:
    """Record of a single step in the agent loop."""

    step_number: int
    """Step number (1-indexed)."""

    tool_call: FaraToolCall
    """The action Fara decided to take."""

    execution_result: ExecutionResult
    """Result of executing the action."""

    screenshot_b64: Optional[str] = None
    """Screenshot taken after action (if any)."""


@dataclass
class AgentResult:
    """Result of running the agent loop."""

    success: bool
    """Whether the goal was achieved (Fara returned terminate)."""

    steps: List[AgentStep] = field(default_factory=list)
    """All steps taken during execution."""

    final_screenshot_b64: Optional[str] = None
    """Final screenshot after completion."""

    reason: Optional[str] = None
    """Explanation if success=False (cancelled, max steps, error)."""

    @property
    def step_count(self) -> int:
        """Number of steps taken."""
        return len(self.steps)


class AgentRunner:
    """
    Run Fara in autonomous loop until terminate or cancelled.

    This orchestrates the Goal -> Screenshot -> Fara -> Execute -> Repeat loop.
    Each step is streamed via MCP progress notifications if a progress token
    is provided.

    ReAct Pattern:
        Implements ReAct (Reasoning + Acting) by including action history in the
        prompt. This gives Fara memory of previous steps so it can reason about
        what's already done and what remains.

    Environment variables:
        FARA_MAX_AGENT_STEPS: Maximum steps before giving up (default: 20)
    """

    def __init__(
        self,
        grounder: "VisualGrounder",
        executor: "PlaywrightExecutor",
        max_steps: Optional[int] = None,
    ):
        """
        Initialize agent runner.

        Args:
            grounder: Visual grounder for getting actions
            executor: Playwright executor for running actions
            max_steps: Max steps (overrides FARA_MAX_AGENT_STEPS env var)
        """
        self.grounder = grounder
        self.executor = executor
        self.max_steps = max_steps or int(
            os.environ.get("FARA_MAX_AGENT_STEPS", "20")
        )

        self._cancelled = False
        self._cancel_reason: Optional[str] = None

    def _format_step(self, step: AgentStep) -> str:
        """Format a single step for history context."""
        tc = step.tool_call
        status = "✓" if step.execution_result.success else "✗"

        # Build action description
        if tc.action == "visit_url":
            desc = f"visit_url: {tc.url}"
        elif tc.action == "type":
            coord_str = f" at {tc.coordinate}" if tc.coordinate else ""
            desc = f"type: '{tc.text}'{coord_str}"
        elif tc.action in ("left_click", "click", "double_click"):
            coord_str = f" at {tc.coordinate}" if tc.coordinate else ""
            desc = f"{tc.action}{coord_str}"
        elif tc.action == "scroll":
            dir_str = tc.direction or ("down" if tc.pixels and tc.pixels < 0 else "up")
            desc = f"scroll {dir_str}"
        elif tc.action == "key":
            desc = f"key: {tc.keys}"
        else:
            desc = tc.action

        return f"[{step.step_number}] {desc} {status}"

    def _build_goal_with_history(self, goal: str, steps: List[AgentStep]) -> str:
        """
        Build goal prompt with ReAct-style action history.

        This gives Fara context about what actions were already taken,
        enabling it to reason about what remains to be done.
        """
        if not steps:
            return goal

        history_lines = [self._format_step(s) for s in steps]
        history_str = "\n".join(history_lines)

        return f"""{goal}

Previous actions:
{history_str}

Based on the current screenshot and previous actions, what is the next action?"""

    def cancel(self, reason: str = "") -> None:
        """
        Cancel the agent loop.

        Called when client sends MCP notifications/cancelled.
        The agent will stop after the current step completes.

        Args:
            reason: Optional reason for cancellation
        """
        self._cancelled = True
        self._cancel_reason = reason
        logger.info(f"Agent cancellation requested: {reason or 'no reason'}")

    def reset(self) -> None:
        """Reset cancellation state for reuse."""
        self._cancelled = False
        self._cancel_reason = None

    async def run(
        self,
        goal: str,
        page: "Page",
        screenshot_fn,
        progress_callback=None,
    ) -> AgentResult:
        """
        Execute goal autonomously until complete or cancelled.

        Args:
            goal: Natural language goal to achieve
            page: Playwright page to operate on
            screenshot_fn: Async function to capture screenshot (returns base64)
            progress_callback: Optional async callback(step, total, message) for progress

        Returns:
            AgentResult with success status and step history
        """
        self.reset()
        steps: List[AgentStep] = []

        logger.info(f"AgentRunner starting: goal='{goal[:50]}...', max_steps={self.max_steps}")

        for step_num in range(1, self.max_steps + 1):
            # Check cancellation before each step
            if self._cancelled:
                logger.info(f"Agent cancelled at step {step_num}")
                return AgentResult(
                    success=False,
                    steps=steps,
                    reason=f"Cancelled: {self._cancel_reason or 'user request'}",
                )

            # Send progress notification
            if progress_callback:
                await progress_callback(
                    step_num,
                    self.max_steps,
                    f"Step {step_num}: Taking screenshot...",
                )

            # Capture current state
            try:
                screenshot_b64 = await screenshot_fn()
            except Exception as e:
                logger.error(f"Screenshot failed at step {step_num}: {e}")
                return AgentResult(
                    success=False,
                    steps=steps,
                    reason=f"Screenshot failed: {e}",
                )

            # Get next action from Fara
            if progress_callback:
                await progress_callback(
                    step_num,
                    self.max_steps,
                    f"Step {step_num}: Analyzing screenshot...",
                )

            try:
                # Build goal with ReAct history context
                augmented_goal = self._build_goal_with_history(goal, steps)

                # Use get_action_with_retry if available, otherwise get_action
                if hasattr(self.grounder, "get_action_with_retry"):
                    tool_call = await self.grounder.get_action_with_retry(augmented_goal, screenshot_b64)
                else:
                    tool_call = await self.grounder.get_action(augmented_goal, screenshot_b64)
            except Exception as e:
                logger.error(f"Fara failed at step {step_num}: {e}")
                return AgentResult(
                    success=False,
                    steps=steps,
                    reason=f"Vision model failed: {e}",
                )

            logger.info(
                f"Step {step_num}: action={tool_call.action}, "
                f"coord={tool_call.coordinate}, confidence={tool_call.confidence:.2f}"
            )

            # Check for terminate action
            if tool_call.action.lower() == "terminate":
                logger.info(f"Agent completed in {step_num} steps (Fara signaled terminate)")

                # Create step record for terminate
                step_record = AgentStep(
                    step_number=step_num,
                    tool_call=tool_call,
                    execution_result=ExecutionResult(success=True, action="terminate"),
                    screenshot_b64=screenshot_b64,
                )
                steps.append(step_record)

                return AgentResult(
                    success=True,
                    steps=steps,
                    final_screenshot_b64=screenshot_b64,
                )

            # Execute the action
            if progress_callback:
                await progress_callback(
                    step_num,
                    self.max_steps,
                    f"Step {step_num}: Executing {tool_call.action}...",
                )

            try:
                execution_result = await self.executor.execute(tool_call, page)
            except Exception as e:
                logger.error(f"Execution failed at step {step_num}: {e}")
                execution_result = ExecutionResult(
                    success=False,
                    action=tool_call.action,
                    error=str(e),
                )

            # Record step
            step_record = AgentStep(
                step_number=step_num,
                tool_call=tool_call,
                execution_result=execution_result,
                screenshot_b64=screenshot_b64,
            )
            steps.append(step_record)

            # Check if execution failed
            if not execution_result.success:
                logger.warning(
                    f"Step {step_num} action failed: {execution_result.error}"
                )
                # Continue anyway - Fara may recover or notice the failure

            # Brief pause to let page settle
            try:
                await page.wait_for_timeout(500)
            except Exception:
                pass

        # Max steps reached
        logger.warning(f"Agent reached max steps ({self.max_steps}) without completing")

        # Get final screenshot
        final_screenshot = None
        try:
            final_screenshot = await screenshot_fn()
        except Exception:
            pass

        return AgentResult(
            success=False,
            steps=steps,
            final_screenshot_b64=final_screenshot,
            reason=f"Max steps ({self.max_steps}) reached without task completion",
        )
