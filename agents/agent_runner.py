"""ReAct-style agent runner for the LaFrieda ERP testbed.

Sends messages and tool definitions to the LLM, executes any requested
tool calls, appends results, and loops until the model returns a final
text answer or the iteration cap is reached.  Supports Anthropic
``tool_use`` format natively.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from agents.tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class AgentResult:
    """Returned by :meth:`AgentRunner.run`."""

    final_answer: str
    trace: List[Tuple[str, Any]] = field(default_factory=list)
    tool_calls_count: int = 0
    iterations: int = 0
    elapsed_seconds: float = 0.0

    def pretty_trace(self) -> str:
        """Human-readable dump of the conversation trace."""
        lines: List[str] = []
        for role, content in self.trace:
            if role == "tool_result":
                lines.append(f"  [tool_result] {_truncate(json.dumps(content), 400)}")
            elif role == "tool_use":
                lines.append(f"  [tool_use] {content.get('name', '?')}({json.dumps(content.get('input', {}))})")
            else:
                text = content if isinstance(content, str) else json.dumps(content)
                lines.append(f"  [{role}] {_truncate(text, 300)}")
        return "\n".join(lines)


def _truncate(s: str, max_len: int) -> str:
    return s if len(s) <= max_len else s[: max_len - 3] + "..."


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

class AgentRunner:
    """Execute a ReAct loop against an Anthropic-compatible LLM.

    Parameters
    ----------
    llm_client:
        An ``anthropic.Anthropic`` client instance (or compatible duck-type
        that exposes ``messages.create``).
    tool_registry:
        :class:`ToolRegistry` with pre-registered tools.
    system_prompt:
        The system prompt that sets the agent persona and context.
    model:
        Model identifier, e.g. ``"claude-sonnet-4-20250514"``.
    max_iterations:
        Hard stop on tool-use loops to prevent runaway spending.
    temperature:
        Sampling temperature forwarded to the LLM.
    confirm_callback:
        Optional ``(tool_name, arguments) -> bool`` gate for tools that
        require confirmation.
    tool_tags:
        If set, only tools matching these tags are exposed to the model.
    """

    def __init__(
        self,
        llm_client,
        tool_registry: ToolRegistry,
        system_prompt: str,
        *,
        model: str = "claude-sonnet-4-20250514",
        max_iterations: int = 10,
        temperature: float = 0.2,
        confirm_callback: Optional[Callable[[str, dict], bool]] = None,
        tool_tags: Optional[List[str]] = None,
    ):
        self.client = llm_client
        self.registry = tool_registry
        self.system_prompt = system_prompt
        self.model = model
        self.max_iterations = max_iterations
        self.temperature = temperature
        self.confirm_callback = confirm_callback
        self.tool_tags = tool_tags

    # -- public API ---------------------------------------------------------

    def run(self, user_message: str) -> AgentResult:
        """Execute the ReAct loop for a single user turn.

        1. Send messages + tools to LLM.
        2. If the response contains ``tool_use`` blocks, execute each tool,
           append results, and loop.
        3. If the response is pure text, return it as the final answer.
        4. Stop at ``max_iterations``.
        """
        t0 = time.monotonic()
        messages: List[dict] = [{"role": "user", "content": user_message}]
        trace: List[Tuple[str, Any]] = [("user", user_message)]
        tool_calls_count = 0
        iterations = 0

        tools_payload = self.registry.get_tools_for_anthropic(tags=self.tool_tags)

        while iterations < self.max_iterations:
            iterations += 1

            # --- call the LLM --------------------------------------------------
            response = self._call_llm(messages, tools_payload)
            stop_reason = response.stop_reason
            content_blocks = response.content

            # --- parse content blocks ------------------------------------------
            text_parts: List[str] = []
            tool_use_blocks: List[dict] = []

            for block in content_blocks:
                if block.type == "text":
                    text_parts.append(block.text)
                    trace.append(("assistant_text", block.text))
                elif block.type == "tool_use":
                    tool_use_blocks.append({
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })
                    trace.append(("tool_use", {"name": block.name, "input": block.input}))

            # --- if no tool calls, we are done ---------------------------------
            if stop_reason == "end_turn" or not tool_use_blocks:
                final = "\n".join(text_parts) if text_parts else "(no response)"
                elapsed = time.monotonic() - t0
                return AgentResult(
                    final_answer=final,
                    trace=trace,
                    tool_calls_count=tool_calls_count,
                    iterations=iterations,
                    elapsed_seconds=round(elapsed, 2),
                )

            # --- execute tool calls and build tool_result messages -------------
            # Append the raw assistant message so the API sees the tool_use
            # blocks it generated.
            messages.append({"role": "assistant", "content": content_blocks})

            tool_result_contents: List[dict] = []
            for tu in tool_use_blocks:
                tool_calls_count += 1
                result = self.registry.execute(
                    tu["name"],
                    tu["input"],
                    confirm_callback=self.confirm_callback,
                )
                trace.append(("tool_result", {"tool_use_id": tu["id"], **result}))
                tool_result_contents.append({
                    "type": "tool_result",
                    "tool_use_id": tu["id"],
                    "content": json.dumps(result, default=str),
                })

            messages.append({"role": "user", "content": tool_result_contents})

        # Exhausted iterations
        final = "\n".join(text_parts) if text_parts else "(max iterations reached without final answer)"
        elapsed = time.monotonic() - t0
        return AgentResult(
            final_answer=final,
            trace=trace,
            tool_calls_count=tool_calls_count,
            iterations=iterations,
            elapsed_seconds=round(elapsed, 2),
        )

    # -- internal -----------------------------------------------------------

    def _call_llm(self, messages: list, tools: list):
        """Single call to the Anthropic messages API."""
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": 4096,
            "temperature": self.temperature,
            "system": self.system_prompt,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools
        return self.client.messages.create(**kwargs)
