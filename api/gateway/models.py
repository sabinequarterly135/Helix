"""Pydantic models for LLM gateway request/response structures."""

from typing import Any

from pydantic import BaseModel


class ChatCompletionRequest(BaseModel):
    """Request body for OpenRouter chat completion API."""

    model: str
    messages: list[dict[str, Any]]
    temperature: float | None = None
    max_tokens: int | None = None
    tools: list[dict] | None = None
    tool_choice: str | dict | None = None
    top_p: float | None = None


class ChatMessage(BaseModel):
    """A single message in a chat completion response."""

    role: str
    content: str | None = None
    tool_calls: list[dict] | None = None
