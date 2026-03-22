"""Async DB query functions for evolution history.

Provides query functions for retrieving evolution run data
from the database via async SQLAlchemy sessions.

Exports:
    get_evolution_history: Get ordered list of runs for a prompt
    get_latest_evolution_run: Get most recent run for a prompt
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.storage.models import EvolutionRun


async def get_evolution_history(
    session: AsyncSession, prompt_id: str, limit: int = 20
) -> list[EvolutionRun]:
    """Query evolution runs for a prompt, ordered by most recent first.

    Args:
        session: An async SQLAlchemy session.
        prompt_id: The prompt identifier to filter by.
        limit: Maximum number of runs to return (default 20).

    Returns:
        List of EvolutionRun objects ordered by created_at descending,
        limited to the specified count. Returns empty list if none found.
    """
    stmt = (
        select(EvolutionRun)
        .where(EvolutionRun.prompt_id == prompt_id)
        .order_by(EvolutionRun.created_at.desc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_latest_evolution_run(session: AsyncSession, prompt_id: str) -> EvolutionRun | None:
    """Get the most recent evolution run for a prompt.

    Args:
        session: An async SQLAlchemy session.
        prompt_id: The prompt identifier to filter by.

    Returns:
        The most recent EvolutionRun, or None if no runs exist.
    """
    runs = await get_evolution_history(session, prompt_id, limit=1)
    return runs[0] if runs else None
