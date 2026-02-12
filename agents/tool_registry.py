"""Tool registry for the LaFrieda ERP agent framework.

Provides a unified registry that stores tool definitions and supports
exporting them in both Anthropic (tool_use) and OpenAI (function_calling)
formats.  Tool execution is dispatched through the registry so that
confirmation-gated tools can be intercepted before running.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool dataclass
# ---------------------------------------------------------------------------

@dataclass
class Tool:
    """A single callable tool with schema metadata."""

    name: str
    description: str
    parameters: dict  # JSON Schema object ({"type": "object", "properties": ...})
    function: Callable
    requires_confirmation: bool = False
    tags: List[str] = field(default_factory=list)

    def __post_init__(self):
        # Ensure the parameters dict always has the expected top-level shape
        if "type" not in self.parameters:
            self.parameters = {
                "type": "object",
                "properties": self.parameters,
                "required": list(self.parameters.keys()),
            }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """Central registry of tools available to agent runners.

    Supports:
    * Registration by ``Tool`` instance or decorator.
    * Export to Anthropic and OpenAI wire formats.
    * Tag-based filtering (e.g. give an agent only "ops" tools).
    * Dispatched execution with optional confirmation callback.
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    # -- registration -------------------------------------------------------

    def register(self, tool: Tool) -> None:
        """Register a *Tool* instance."""
        if tool.name in self._tools:
            logger.warning("Overwriting existing tool '%s'", tool.name)
        self._tools[tool.name] = tool

    def register_many(self, tools: List[Tool]) -> None:
        for t in tools:
            self.register(t)

    # -- lookup -------------------------------------------------------------

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self, tags: Optional[List[str]] = None) -> List[Tool]:
        """Return all tools, optionally filtered to those matching *any* tag."""
        if tags is None:
            return list(self._tools.values())
        tag_set = set(tags)
        return [t for t in self._tools.values() if tag_set & set(t.tags)]

    @property
    def tool_names(self) -> List[str]:
        return list(self._tools.keys())

    # -- export for LLM providers -------------------------------------------

    def get_tools_for_anthropic(
        self, tags: Optional[List[str]] = None
    ) -> List[dict]:
        """Return tool definitions in the Anthropic ``tools`` format.

        Each entry:
        ```
        {
          "name": "...",
          "description": "...",
          "input_schema": { ... JSON Schema ... }
        }
        ```
        """
        out: List[dict] = []
        for tool in self.list_tools(tags):
            out.append({
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.parameters,
            })
        return out

    def get_tools_for_openai(
        self, tags: Optional[List[str]] = None
    ) -> List[dict]:
        """Return tool definitions in the OpenAI *function_calling* format.

        Each entry:
        ```
        {
          "type": "function",
          "function": {
            "name": "...",
            "description": "...",
            "parameters": { ... JSON Schema ... }
          }
        }
        ```
        """
        out: List[dict] = []
        for tool in self.list_tools(tags):
            out.append({
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            })
        return out

    # -- execution ----------------------------------------------------------

    def execute(
        self,
        tool_name: str,
        arguments: dict,
        *,
        confirm_callback: Optional[Callable[[str, dict], bool]] = None,
    ) -> dict:
        """Execute a registered tool by name.

        Parameters
        ----------
        tool_name:
            Name of the tool to execute.
        arguments:
            Keyword arguments to forward to the tool function.
        confirm_callback:
            Optional callable ``(tool_name, arguments) -> bool``.  If the
            tool has ``requires_confirmation=True`` and this callback is
            provided, the tool will only run when the callback returns
            ``True``.

        Returns
        -------
        dict with ``{"status": "success"|"error", ...}``
        """
        tool = self._tools.get(tool_name)
        if tool is None:
            return {
                "status": "error",
                "error": f"Unknown tool: {tool_name}",
            }

        # Confirmation gate
        if tool.requires_confirmation:
            if confirm_callback is not None:
                if not confirm_callback(tool_name, arguments):
                    return {
                        "status": "error",
                        "error": f"Tool '{tool_name}' execution was denied by confirmation callback.",
                    }
            else:
                logger.warning(
                    "Tool '%s' requires confirmation but no callback was provided. "
                    "Executing anyway.",
                    tool_name,
                )

        try:
            result = tool.function(**arguments)
            if not isinstance(result, dict):
                result = {"result": result}
            result.setdefault("status", "success")
            return result
        except Exception as exc:
            logger.exception("Tool '%s' raised an exception", tool_name)
            return {
                "status": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }
