"""Configuration models with three-layer cascade: gene.yaml < env vars < constructor args."""

from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict, YamlConfigSettingsSource


class GenerationConfig(BaseModel):
    """Generation hyperparameters for LLM calls."""

    temperature: float = 0.7
    max_tokens: int = 4096
    top_p: float | None = None
    top_k: int | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None


class GeneConfig(BaseSettings):
    """Main configuration for Helix.

    Three-layer cascade priority:
    1. Constructor args / CLI flags (highest)
    2. Environment variables (GENE_ prefix)
    3. gene.yaml file (lowest)

    Required for commands that use external services (evolve, history, status, bootstrap):
    openrouter_api_key and database_url. File-only commands (register, add-case, diff)
    work without these fields configured.

    Pass _yaml_file="path/to/gene.yaml" to constructor to override
    the default YAML file path (useful for testing).
    """

    model_config = SettingsConfigDict(
        env_prefix="GENE_",
        env_nested_delimiter="__",
    )

    # Secrets (optional -- validated at command level where needed)
    openrouter_api_key: str | None = None
    gemini_api_key: str | None = None
    openai_api_key: str | None = None
    database_url: str | None = None

    # Model configuration
    meta_model: str = "anthropic/claude-sonnet-4"
    target_model: str = "openai/gpt-4o-mini"
    judge_model: str = "anthropic/claude-sonnet-4"

    # Provider selection per role (openrouter, gemini, or openai)
    meta_provider: str = "openrouter"
    target_provider: str = "openrouter"
    judge_provider: str = "openrouter"

    # Per-role thinking budgets (Gemini 2.5 series: token count, 0=off, -1=dynamic)
    meta_thinking_budget: int | None = None
    target_thinking_budget: int | None = None
    judge_thinking_budget: int | None = None

    # Per-role temperature overrides (None = use generation.temperature fallback)
    meta_temperature: float | None = None
    target_temperature: float | None = None
    judge_temperature: float | None = None

    # Runtime settings
    concurrency_limit: int = 10
    prompts_dir: str = "./prompts"

    # Generation defaults
    generation: GenerationConfig = GenerationConfig()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings,
        env_settings,
        dotenv_settings,
        file_secret_settings,
    ):
        """Configure source priority: init (constructor) > env > yaml.

        Accepts _yaml_file in init_kwargs to override the default gene.yaml path.
        """
        # Extract _yaml_file from init_kwargs (pop so it doesn't get validated as a field)
        yaml_file = init_settings.init_kwargs.pop("_yaml_file", None)
        yaml_path = yaml_file if yaml_file else "gene.yaml"

        return (
            init_settings,
            env_settings,
            YamlConfigSettingsSource(
                settings_cls,
                yaml_file=Path(yaml_path),
            ),
        )
