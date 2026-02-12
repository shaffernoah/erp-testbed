"""Multi-provider LLM client for the LaFrieda ERP analysis framework.

Supports Anthropic (Claude) and OpenAI providers with a unified interface
for completions and structured JSON responses.
"""

import json
import logging
from typing import Any, Optional

from config.settings import (
    ANALYSIS_DEFAULT_TEMPERATURE,
    ANTHROPIC_API_KEY,
    LLM_MODEL,
    LLM_PROVIDER,
    OPENAI_API_KEY,
)

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client supporting Anthropic and OpenAI providers.

    Parameters
    ----------
    provider : str
        LLM provider name -- ``"anthropic"`` or ``"openai"``.
        Defaults to ``config.settings.LLM_PROVIDER``.
    model : str | None
        Model identifier.  Defaults to ``config.settings.LLM_MODEL``.
    api_key : str | None
        API key override.  When *None*, the key is read from
        ``config.settings`` for the chosen provider.
    """

    SUPPORTED_PROVIDERS = {"anthropic", "openai"}

    def __init__(
        self,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        self.provider = (provider or LLM_PROVIDER).lower()
        if self.provider not in self.SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Unsupported provider '{self.provider}'. "
                f"Choose from {self.SUPPORTED_PROVIDERS}."
            )

        self.model = model or LLM_MODEL
        self._api_key = api_key or self._resolve_api_key()
        self._client = self._build_client()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_api_key(self) -> str:
        """Return the correct API key from settings for the provider."""
        if self.provider == "anthropic":
            key = ANTHROPIC_API_KEY
        else:
            key = OPENAI_API_KEY

        if not key:
            raise ValueError(
                f"No API key configured for provider '{self.provider}'. "
                f"Set the appropriate environment variable."
            )
        return key

    def _build_client(self) -> Any:
        """Lazily import the provider SDK and return a client instance."""
        if self.provider == "anthropic":
            try:
                import anthropic  # type: ignore[import-untyped]
            except ImportError as exc:
                raise ImportError(
                    "The 'anthropic' package is required for the Anthropic "
                    "provider. Install it with: pip install anthropic"
                ) from exc
            return anthropic.Anthropic(api_key=self._api_key)

        # openai
        try:
            import openai  # type: ignore[import-untyped]
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required for the OpenAI provider. "
                "Install it with: pip install openai"
            ) from exc
        return openai.OpenAI(api_key=self._api_key)

    # ------------------------------------------------------------------
    # Provider-specific completion dispatchers
    # ------------------------------------------------------------------

    def _complete_anthropic(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        tools: Optional[list[dict]],
    ) -> dict:
        """Call the Anthropic Messages API."""
        # Separate a system message (if present) from the rest.
        system_text: Optional[str] = None
        api_messages: list[dict] = []
        for msg in messages:
            if msg["role"] == "system":
                system_text = msg["content"]
            else:
                api_messages.append(msg)

        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": api_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if system_text:
            kwargs["system"] = system_text
        if tools:
            kwargs["tools"] = tools

        response = self._client.messages.create(**kwargs)

        content_text = ""
        tool_calls: list[dict] = []
        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )

        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

        return {
            "content": content_text,
            "tool_calls": tool_calls,
            "usage": usage,
        }

    def _complete_openai(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int,
        tools: Optional[list[dict]],
    ) -> dict:
        """Call the OpenAI Chat Completions API."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if tools:
            # Convert to OpenAI function-calling schema.
            kwargs["tools"] = [
                {"type": "function", "function": t} for t in tools
            ]

        response = self._client.chat.completions.create(**kwargs)
        choice = response.choices[0]

        content_text = choice.message.content or ""
        tool_calls: list[dict] = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls.append(
                    {
                        "id": tc.id,
                        "name": tc.function.name,
                        "input": json.loads(tc.function.arguments),
                    }
                )

        usage = {
            "input_tokens": response.usage.prompt_tokens,
            "output_tokens": response.usage.completion_tokens,
        }

        return {
            "content": content_text,
            "tool_calls": tool_calls,
            "usage": usage,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def complete(
        self,
        messages: list[dict],
        temperature: float = ANALYSIS_DEFAULT_TEMPERATURE,
        max_tokens: int = 4096,
        tools: Optional[list[dict]] = None,
    ) -> dict:
        """Send a completion request and return a normalised response.

        Parameters
        ----------
        messages : list[dict]
            Conversation messages in ``{"role": ..., "content": ...}`` format.
            A ``"system"`` role message is supported for both providers.
        temperature : float
            Sampling temperature.
        max_tokens : int
            Maximum tokens in the response.
        tools : list[dict] | None
            Tool / function definitions for tool-use requests.

        Returns
        -------
        dict
            ``{"content": str, "tool_calls": list, "usage": dict}``
        """
        logger.debug(
            "LLM request: provider=%s model=%s msgs=%d temp=%.2f",
            self.provider,
            self.model,
            len(messages),
            temperature,
        )

        if self.provider == "anthropic":
            result = self._complete_anthropic(
                messages, temperature, max_tokens, tools
            )
        else:
            result = self._complete_openai(
                messages, temperature, max_tokens, tools
            )

        logger.debug(
            "LLM response: tokens_in=%s tokens_out=%s",
            result["usage"].get("input_tokens"),
            result["usage"].get("output_tokens"),
        )
        return result

    def complete_json(
        self,
        messages: list[dict],
        temperature: float = ANALYSIS_DEFAULT_TEMPERATURE,
        max_tokens: int = 4096,
    ) -> dict:
        """Send a completion request and parse the response as JSON.

        The LLM is expected to return valid JSON (prompted via the system
        message).  This method extracts the first JSON object or array
        from the response text.

        Returns
        -------
        dict | list
            The parsed JSON structure.

        Raises
        ------
        ValueError
            If no valid JSON can be extracted from the response.
        """
        result = self.complete(
            messages, temperature=temperature, max_tokens=max_tokens
        )
        raw = result["content"].strip()

        # Try direct parse first.
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Strip markdown code fences if present.
        if raw.startswith("```"):
            lines = raw.split("\n")
            # Remove first and last fence lines.
            lines = [
                ln
                for ln in lines
                if not ln.strip().startswith("```")
            ]
            raw = "\n".join(lines).strip()
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                pass

        # Last resort: find the first { ... } or [ ... ] span.
        for open_char, close_char in [("{", "}"), ("[", "]")]:
            start = raw.find(open_char)
            if start == -1:
                continue
            depth = 0
            for i in range(start, len(raw)):
                if raw[i] == open_char:
                    depth += 1
                elif raw[i] == close_char:
                    depth -= 1
                if depth == 0:
                    try:
                        return json.loads(raw[start : i + 1])
                    except json.JSONDecodeError:
                        break

        raise ValueError(
            f"Could not parse JSON from LLM response:\n{result['content'][:500]}"
        )
