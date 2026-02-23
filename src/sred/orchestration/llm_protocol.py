"""Minimal LLMClient protocol for orchestration nodes.

Stepping stone toward the full Bible §5 LLMClient interface at
``src/sred/infra/llm/client.py``.  Covers only the planner's need:
structured JSON output from chat completions.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for chat completion calls returning a content string."""

    def chat_completions_create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Return the content string from the first choice."""
        ...


class OpenAILLMClient:
    """Adapter wrapping the existing OpenAI SDK client."""

    def __init__(self, openai_client: Any | None = None) -> None:
        if openai_client is not None:
            self._client = openai_client
        else:
            from sred.llm.openai_client import client  # lazy import

            self._client = client

    def chat_completions_create(
        self,
        *,
        model: str,
        messages: list[dict[str, Any]],
        response_format: dict[str, Any] | None = None,
    ) -> str:
        """Delegate to the OpenAI SDK and return the content string."""
        kwargs: dict[str, Any] = {
            "model": model,
            "messages": messages,
        }
        if response_format is not None:
            kwargs["response_format"] = response_format
        response = self._client.chat.completions.create(**kwargs)
        return response.choices[0].message.content
