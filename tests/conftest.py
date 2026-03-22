"""Shared test fixtures for Helix."""

from pathlib import Path

import pytest


@pytest.fixture
def tmp_prompts_dir(tmp_path: Path) -> Path:
    """Create a temporary directory for prompt storage in tests."""
    prompts_dir = tmp_path / "prompts"
    prompts_dir.mkdir()
    return prompts_dir


@pytest.fixture
def sample_gene_config():
    """Create a GeneConfig with test values using constructor args (no env vars needed)."""
    from api.config.models import GeneConfig

    return GeneConfig(
        openrouter_api_key="test-api-key-12345",
        database_url="postgresql://test:test@localhost:5432/test_gene",
        meta_model="anthropic/claude-sonnet-4",
        target_model="openai/gpt-4o-mini",
        judge_model="anthropic/claude-sonnet-4",
        concurrency_limit=5,
        prompts_dir="./test-prompts",
    )
