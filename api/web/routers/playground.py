"""Playground API endpoint for interactive chat with streaming SSE responses,
playground variable persistence, and playground config persistence endpoints.

Provides:
- POST /{prompt_id}/chat for sending messages and receiving
  LLM responses token-by-token via Server-Sent Events (SSE).
- GET /{prompt_id}/variables for loading saved variable values from DB.
- PUT /{prompt_id}/variables for saving variable values to DB (upsert).
- GET /{prompt_id}/playground-config for loading playground turn_limit/budget from DB.
- PUT /{prompt_id}/playground-config for saving playground turn_limit/budget to DB.

The chat endpoint renders the prompt template as a system message, builds
the conversation context, and streams the target model's response.
Config cascade (global -> prompt-level) is respected for model/provider selection.
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import StreamingResponse

from api.config.models import GeneConfig
from api.evaluation.renderer import TemplateRenderer
from api.gateway.cost import estimate_cost_from_tokens
from api.gateway.factory import create_provider
from api.registry.service import PromptRegistry
from api.storage.models import PlaygroundVariable, PromptConfig
from api.web.deps import get_config, get_db_session, get_registry
from api.web.schemas import (
    ChatRequest,
    PlaygroundConfigResponse,
    PlaygroundConfigUpdateRequest,
    PlaygroundVariablesResponse,
    PlaygroundVariablesUpdateRequest,
)

router = APIRouter()

logger = logging.getLogger(__name__)


@router.get("/{prompt_id}/variables", response_model=PlaygroundVariablesResponse)
async def get_variables(
    prompt_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> PlaygroundVariablesResponse:
    """Return all saved variable values for a prompt from DB."""
    stmt = select(PlaygroundVariable).where(PlaygroundVariable.prompt_id == prompt_id)
    result = await session.execute(stmt)
    rows = result.scalars().all()
    variables = {row.variable_name: row.value for row in rows}
    return PlaygroundVariablesResponse(prompt_id=prompt_id, variables=variables)


@router.put("/{prompt_id}/variables", response_model=PlaygroundVariablesResponse)
async def save_variables(
    prompt_id: str,
    body: PlaygroundVariablesUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> PlaygroundVariablesResponse:
    """Save variable values to DB (upsert per variable_name).

    For each variable in the request, check if (prompt_id, variable_name)
    exists; if yes update value, if no insert new row.
    """
    for var_name, var_value in body.variables.items():
        stmt = select(PlaygroundVariable).where(
            PlaygroundVariable.prompt_id == prompt_id,
            PlaygroundVariable.variable_name == var_name,
        )
        result = await session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing is not None:
            existing.value = var_value
        else:
            session.add(
                PlaygroundVariable(
                    prompt_id=prompt_id,
                    variable_name=var_name,
                    value=var_value,
                )
            )

    await session.commit()

    # Return the full set of variables for this prompt
    stmt = select(PlaygroundVariable).where(PlaygroundVariable.prompt_id == prompt_id)
    result = await session.execute(stmt)
    rows = result.scalars().all()
    variables = {row.variable_name: row.value for row in rows}
    return PlaygroundVariablesResponse(prompt_id=prompt_id, variables=variables)


@router.get("/{prompt_id}/playground-config", response_model=PlaygroundConfigResponse)
async def get_playground_config(
    prompt_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> PlaygroundConfigResponse:
    """Return playground config (turn_limit, budget) for a prompt."""
    result = await session.execute(
        select(PromptConfig).where(PromptConfig.prompt_id == prompt_id)
    )
    row = result.scalar_one_or_none()
    return PlaygroundConfigResponse(
        turn_limit=row.playground_turn_limit if row else None,
        budget=row.playground_budget if row else None,
    )


@router.put("/{prompt_id}/playground-config", response_model=PlaygroundConfigResponse)
async def update_playground_config(
    prompt_id: str,
    body: PlaygroundConfigUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
) -> PlaygroundConfigResponse:
    """Update playground config (turn_limit, budget) for a prompt."""
    result = await session.execute(
        select(PromptConfig).where(PromptConfig.prompt_id == prompt_id)
    )
    row = result.scalar_one_or_none()
    if row:
        if body.turn_limit is not None:
            row.playground_turn_limit = body.turn_limit
        if body.budget is not None:
            row.playground_budget = body.budget
    else:
        row = PromptConfig(
            prompt_id=prompt_id,
            playground_turn_limit=body.turn_limit,
            playground_budget=body.budget,
        )
        session.add(row)
    await session.commit()
    return PlaygroundConfigResponse(
        turn_limit=row.playground_turn_limit,
        budget=row.playground_budget,
    )


def _sse_event(event: str, data: dict) -> str:
    """Format a single SSE event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


@router.post("/{prompt_id}/chat")
async def chat(
    prompt_id: str,
    body: ChatRequest,
    config: GeneConfig = Depends(get_config),
    registry: PromptRegistry = Depends(get_registry),
    session: AsyncSession = Depends(get_db_session),
):
    """Stream an LLM chat response via Server-Sent Events.

    Loads the prompt template from DB, renders it with provided variables as the
    system message, appends the conversation history, and streams the
    target model's response token-by-token.

    SSE events emitted:
    - token: {"content": "..."} -- each streamed token
    - done: {"input_tokens": N, "output_tokens": N, "cost_usd": F, "model": "...", "finish_reason": "..."} -- stream complete
    - error: {"message": "..."} -- on failure
    - limit_reached: {"reason": "turn_limit", "turns_used": N, "turn_limit": N} -- turn limit exceeded
    """
    # Load prompt from DB via registry
    record = await registry.load_prompt(prompt_id, config)

    # Get merged config from the record (includes per-prompt overrides)
    merged_config = record.config if record.config else config

    # Determine turn limit: DB config > request body
    db_turn_limit = None
    result = await session.execute(
        select(PromptConfig).where(PromptConfig.prompt_id == prompt_id)
    )
    config_row = result.scalar_one_or_none()
    if config_row and config_row.playground_turn_limit is not None:
        db_turn_limit = config_row.playground_turn_limit

    effective_turn_limit = db_turn_limit if db_turn_limit is not None else body.turn_limit

    # Check turn limit: count user messages
    user_turn_count = sum(1 for m in body.messages if m.get("role") == "user")
    if user_turn_count > effective_turn_limit:
        return StreamingResponse(
            _limit_reached_generator(user_turn_count, effective_turn_limit),
            media_type="text/event-stream",
        )

    # Get template from DB-loaded record
    template_source = record.template
    if not template_source:
        raise HTTPException(
            status_code=404,
            detail=f"Prompt template not found for '{prompt_id}'",
        )

    renderer = TemplateRenderer()

    try:
        system_prompt = renderer.render(template_source, body.variables)
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Template rendering failed: {e}",
        ) from e

    # Build full message list: system + conversation history
    messages = [{"role": "system", "content": system_prompt}, *body.messages]

    return StreamingResponse(
        _sse_generator(merged_config, messages),
        media_type="text/event-stream",
    )


async def _limit_reached_generator(turns_used: int, turn_limit: int):
    """Yield a single limit_reached SSE event and close."""
    yield _sse_event(
        "limit_reached",
        {
            "reason": "turn_limit",
            "turns_used": turns_used,
            "turn_limit": turn_limit,
        },
    )


async def _sse_generator(config: GeneConfig, messages: list[dict]):
    """Stream LLM response tokens as SSE events.

    Creates a provider from the merged config, calls the target model
    with streaming enabled, and yields token events followed by a done event.
    """
    provider = create_provider(config.target_provider, config)

    target_model = provider._normalize_model(config.target_model)
    temperature = config.target_temperature or config.generation.temperature

    # Build streaming kwargs
    kwargs: dict = {
        "temperature": temperature,
        "stream_options": {"include_usage": True},
    }

    # Add thinking budget if configured (Gemini 2.5 series)
    if config.target_thinking_budget is not None and config.target_thinking_budget != 0:
        kwargs["extra_body"] = {
            "thinking": {
                "type": "enabled",
                "budget_tokens": config.target_thinking_budget,
            }
        }

    input_tokens = 0
    output_tokens = 0
    finish_reason = "stop"

    try:
        stream = await provider._client.chat.completions.create(
            model=target_model,
            messages=messages,
            stream=True,
            **kwargs,
        )

        async for chunk in stream:
            # Extract usage from the final chunk (when stream_options.include_usage is True)
            if chunk.usage is not None:
                input_tokens = chunk.usage.prompt_tokens or 0
                output_tokens = chunk.usage.completion_tokens or 0

            if chunk.choices:
                choice = chunk.choices[0]
                if choice.finish_reason is not None:
                    finish_reason = choice.finish_reason

                delta = choice.delta
                if delta and delta.content is not None:
                    yield _sse_event("token", {"content": delta.content})

        # Compute cost
        cost_usd = estimate_cost_from_tokens(target_model, input_tokens, output_tokens)

        yield _sse_event(
            "done",
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cost_usd": cost_usd if cost_usd is not None else 0.0,
                "model": target_model,
                "finish_reason": finish_reason,
            },
        )

    except Exception as e:
        logger.exception("SSE streaming error for model %s", target_model)
        yield _sse_event("error", {"message": str(e)})

    finally:
        await provider.close()
