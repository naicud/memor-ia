"""Main agentic loop — drives agent execution via async generator pattern.

Mirrors the TypeScript query.ts loop:
1. Call model with messages
2. Collect response (stream)
3. Execute tools
4. Append results
5. Check exit conditions
6. Repeat
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Callable,
    Optional,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class StopReason(str, Enum):
    """Why an agent run stopped."""
    END_TURN = "end_turn"
    MAX_TURNS = "max_turns"
    ABORT = "abort"
    ERROR = "error"
    STOP_HOOK = "stop_hook"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RunnerConfig:
    """Configuration for an agent runner."""
    max_turns: int = 200
    model: str = "sonnet"
    query_source: str = "agent"
    skip_transcript: bool = False


@dataclass
class TurnResult:
    """Result of a single agent turn."""
    messages: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    stop_reason: Optional[StopReason] = None
    usage: dict = field(default_factory=dict)


@dataclass
class AgentResult:
    """Final result of agent execution."""
    agent_id: str
    content: str
    total_tool_use_count: int = 0
    total_duration_ms: float = 0
    total_tokens: int = 0
    turns: int = 0
    stop_reason: StopReason = StopReason.END_TURN
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# AgentRunner
# ---------------------------------------------------------------------------

class AgentRunner:
    """Main agentic loop — executes an agent step by step.

    The runner is an async generator that yields :class:`TurnResult` objects,
    one per model invocation cycle.
    """

    def __init__(
        self,
        config: RunnerConfig,
        execute_tool: Callable[..., Any],
        call_model: Callable[..., Any],
        agent_context: Any = None,
    ) -> None:
        self._config = config
        self._execute_tool = execute_tool
        self._call_model = call_model
        self._context = agent_context
        self._turn_count: int = 0
        self._start_time: float = time.time()
        self._messages: list[dict] = []
        self._stop_hooks: list[Callable[..., Any]] = []
        self._on_turn_complete: list[Callable[..., Any]] = []

        # Aggregation accumulators
        self._total_tool_use_count: int = 0
        self._total_tokens: int = 0
        self._last_text_content: str = ""
        self._final_stop_reason: StopReason = StopReason.END_TURN
        self._final_error: Optional[str] = None

    # -- public API ----------------------------------------------------------

    async def run(
        self, initial_messages: list[dict]
    ) -> AsyncGenerator[TurnResult, None]:
        """Execute the agent loop, yielding turn results."""
        self._messages = list(initial_messages)

        while self._turn_count < self._config.max_turns:
            # Check abort
            if self._is_aborted():
                turn = TurnResult(messages=[], stop_reason=StopReason.ABORT)
                self._final_stop_reason = StopReason.ABORT
                yield turn
                return

            self._turn_count += 1

            # Call model
            try:
                response = await self._call_model(self._messages)
            except Exception as exc:
                logger.error("Model call failed on turn %d: %s", self._turn_count, exc)
                turn = TurnResult(messages=[], stop_reason=StopReason.ERROR)
                self._final_stop_reason = StopReason.ERROR
                self._final_error = str(exc)
                yield turn
                return

            # Build turn result
            turn = TurnResult(messages=[response])

            # Accumulate usage
            resp_usage = response.get("usage", {})
            turn.usage = resp_usage
            self._total_tokens += resp_usage.get("total_tokens", 0)

            # Capture last assistant text
            self._capture_text(response)

            # Check for tool calls
            tool_calls = self._extract_tool_calls(response)
            if not tool_calls:
                turn.stop_reason = StopReason.END_TURN
                self._final_stop_reason = StopReason.END_TURN
                self._messages.append(response)
                yield turn
                return

            # Execute tools
            turn.tool_calls = tool_calls
            self._total_tool_use_count += len(tool_calls)
            self._messages.append(response)

            for tc in tool_calls:
                result = await self._execute_tool(tc)
                turn.tool_results.append(result)
                self._messages.append(result)

            # Run stop hooks
            should_stop = False
            for hook in self._stop_hooks:
                hook_result = hook(self._messages, turn)
                if asyncio.iscoroutine(hook_result):
                    hook_result = await hook_result
                if hook_result:
                    turn.stop_reason = StopReason.STOP_HOOK
                    self._final_stop_reason = StopReason.STOP_HOOK
                    should_stop = True
                    break

            # Notify listeners
            for cb in self._on_turn_complete:
                cb(turn)

            yield turn

            if should_stop:
                return

        # Max turns reached
        self._final_stop_reason = StopReason.MAX_TURNS
        yield TurnResult(messages=[], stop_reason=StopReason.MAX_TURNS)

    def add_stop_hook(self, hook: Callable[..., Any]) -> None:
        """Register a stop hook.

        *hook(messages, turn)* → truthy to stop the loop.
        """
        self._stop_hooks.append(hook)

    def on_turn_complete(self, callback: Callable[..., Any]) -> None:
        """Register a per-turn completion callback."""
        self._on_turn_complete.append(callback)

    def get_result(self, agent_id: str = "") -> AgentResult:
        """Aggregate final result from all turns."""
        return AgentResult(
            agent_id=agent_id,
            content=self._last_text_content,
            total_tool_use_count=self._total_tool_use_count,
            total_duration_ms=self.elapsed_ms,
            total_tokens=self._total_tokens,
            turns=self._turn_count,
            stop_reason=self._final_stop_reason,
            error=self._final_error,
        )

    # -- properties ----------------------------------------------------------

    @property
    def turn_count(self) -> int:
        return self._turn_count

    @property
    def elapsed_ms(self) -> float:
        return (time.time() - self._start_time) * 1000

    @property
    def messages(self) -> list[dict]:
        """Current message history (read-only snapshot)."""
        return list(self._messages)

    # -- internals -----------------------------------------------------------

    def _is_aborted(self) -> bool:
        if self._context is None:
            return False
        abort = getattr(self._context, "abort_event", None)
        if abort is None:
            return False
        return abort.is_set()

    def _extract_tool_calls(self, response: dict) -> list[dict]:
        """Extract tool_use blocks from a model response."""
        content = response.get("content", [])
        if isinstance(content, list):
            return [
                block for block in content
                if isinstance(block, dict) and block.get("type") == "tool_use"
            ]
        return []

    def _capture_text(self, response: dict) -> None:
        """Capture the latest assistant text from the response."""
        content = response.get("content", [])
        if isinstance(content, str):
            self._last_text_content = content
            return
        if isinstance(content, list):
            texts: list[str] = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
            if texts:
                self._last_text_content = "\n".join(texts)
