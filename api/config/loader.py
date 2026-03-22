"""Config loading with error handling and per-prompt override merging."""

import json
from pathlib import Path

from api.config.models import GeneConfig, GenerationConfig
from api.exceptions import ConfigError


def load_config(**overrides) -> GeneConfig:
    """Load GeneConfig with optional overrides passed as constructor args.

    Wraps GeneConfig instantiation with error handling.
    Raises ConfigError on validation failures.
    """
    try:
        return GeneConfig(**overrides)
    except Exception as e:
        raise ConfigError(f"Failed to load configuration: {e}") from e


def load_prompt_config(
    base_config: GeneConfig,
    prompt_dir: Path | None = None,
    overrides_dict: dict | None = None,
) -> GeneConfig:
    """Load per-prompt config overrides and merge onto base config.

    If overrides_dict is provided (from DB), uses it directly.
    Otherwise falls back to reading config.json from prompt_dir (CLI backward compat).

    Returns new GeneConfig with per-prompt overrides applied.
    If no overrides found, returns the base config unchanged.
    """
    if overrides_dict is None:
        if prompt_dir is None:
            return base_config
        # Fallback: read config.json for CLI usage
        config_path = prompt_dir / "config.json"
        if not config_path.exists():
            return base_config

        try:
            with open(config_path) as f:
                overrides_dict = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            raise ConfigError(f"Failed to read prompt config at {config_path}: {e}") from e

    if not overrides_dict:
        return base_config

    # Handle nested generation config
    update_dict = {}
    for key, value in overrides_dict.items():
        if key == "generation" and isinstance(value, dict):
            # Merge generation overrides onto existing generation config
            current_gen = base_config.generation.model_dump()
            current_gen.update(value)
            update_dict["generation"] = GenerationConfig(**current_gen)
        else:
            update_dict[key] = value

    return base_config.model_copy(update=update_dict)
