"""Tests for GeneConfig, GenerationConfig, and config loading.

Covers requirements: MODEL-01, MODEL-02, MODEL-03
"""

import json
from pathlib import Path

import pytest


class TestMetaModelConfig:
    """MODEL-01: GeneConfig has meta_model field."""

    def test_meta_model_default(self):
        """meta_model defaults to anthropic/claude-sonnet-4."""
        from api.config.models import GeneConfig

        config = GeneConfig(
            openrouter_api_key="test-key",
            database_url="postgresql://test@localhost/test",
            _yaml_file="/dev/null",
        )
        assert config.meta_model == "anthropic/claude-sonnet-4"

    def test_meta_model_override_via_constructor(self):
        """meta_model can be overridden via constructor."""
        from api.config.models import GeneConfig

        config = GeneConfig(
            openrouter_api_key="test-key",
            database_url="postgresql://test@localhost/test",
            meta_model="google/gemini-2.5-pro",
        )
        assert config.meta_model == "google/gemini-2.5-pro"


class TestTargetModelConfig:
    """MODEL-02: GeneConfig has target_model field."""

    def test_target_model_default(self):
        """target_model defaults to openai/gpt-4o-mini."""
        from api.config.models import GeneConfig

        config = GeneConfig(
            openrouter_api_key="test-key",
            database_url="postgresql://test@localhost/test",
            _yaml_file="/dev/null",
        )
        assert config.target_model == "openai/gpt-4o-mini"

    def test_target_model_override_via_constructor(self):
        """target_model can be overridden via constructor."""
        from api.config.models import GeneConfig

        config = GeneConfig(
            openrouter_api_key="test-key",
            database_url="postgresql://test@localhost/test",
            target_model="anthropic/claude-haiku-3.5",
        )
        assert config.target_model == "anthropic/claude-haiku-3.5"


class TestJudgeModelConfig:
    """MODEL-03: GeneConfig has judge_model field."""

    def test_judge_model_default(self):
        """judge_model defaults to anthropic/claude-sonnet-4."""
        from api.config.models import GeneConfig

        config = GeneConfig(
            openrouter_api_key="test-key",
            database_url="postgresql://test@localhost/test",
            _yaml_file="/dev/null",
        )
        assert config.judge_model == "anthropic/claude-sonnet-4"

    def test_judge_model_override_via_constructor(self):
        """judge_model can be overridden via constructor."""
        from api.config.models import GeneConfig

        config = GeneConfig(
            openrouter_api_key="test-key",
            database_url="postgresql://test@localhost/test",
            judge_model="openai/gpt-4o",
        )
        assert config.judge_model == "openai/gpt-4o"


class TestGeneConfigYaml:
    """Test 4: GeneConfig loads from YAML file when present."""

    def test_loads_from_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Write a temp gene.yaml, verify values are loaded."""
        yaml_content = """\
meta_model: "google/gemini-2.5-pro"
target_model: "anthropic/claude-haiku-3.5"
concurrency_limit: 20
"""
        yaml_file = tmp_path / "gene.yaml"
        yaml_file.write_text(yaml_content)

        from api.config.models import GeneConfig

        # Must provide required fields via constructor since they're not in YAML
        config = GeneConfig(
            openrouter_api_key="test-key",
            database_url="postgresql://test@localhost/test",
            _yaml_file=str(yaml_file),
        )
        assert config.meta_model == "google/gemini-2.5-pro"
        assert config.target_model == "anthropic/claude-haiku-3.5"
        assert config.concurrency_limit == 20


class TestConfigCascade:
    """Test 5: Constructor args override YAML values (three-layer cascade)."""

    def test_constructor_overrides_yaml(self, tmp_path: Path):
        """Three-layer cascade priority: init > env > yaml."""
        yaml_content = """\
meta_model: "yaml-model"
target_model: "yaml-target"
"""
        yaml_file = tmp_path / "gene.yaml"
        yaml_file.write_text(yaml_content)

        from api.config.models import GeneConfig

        config = GeneConfig(
            openrouter_api_key="test-key",
            database_url="postgresql://test@localhost/test",
            meta_model="constructor-model",
            _yaml_file=str(yaml_file),
        )
        # Constructor wins over YAML
        assert config.meta_model == "constructor-model"
        # YAML value loaded where no constructor override
        assert config.target_model == "yaml-target"


class TestEnvVarOverrides:
    """Test 6: Environment variables with GENE_ prefix override YAML values."""

    def test_env_overrides_yaml(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        """Set GENE_META_MODEL env var, verify it takes precedence over yaml."""
        yaml_content = """\
meta_model: "yaml-model"
"""
        yaml_file = tmp_path / "gene.yaml"
        yaml_file.write_text(yaml_content)

        monkeypatch.setenv("GENE_META_MODEL", "env-model")
        monkeypatch.setenv("GENE_OPENROUTER_API_KEY", "env-key")
        monkeypatch.setenv("GENE_DATABASE_URL", "postgresql://env@localhost/test")

        from api.config.models import GeneConfig

        config = GeneConfig(_yaml_file=str(yaml_file))
        assert config.meta_model == "env-model"
        assert config.openrouter_api_key == "env-key"

    def test_constructor_overrides_env(self, monkeypatch: pytest.MonkeyPatch):
        """Constructor args win over env vars."""
        monkeypatch.setenv("GENE_META_MODEL", "env-model")
        monkeypatch.setenv("GENE_OPENROUTER_API_KEY", "env-key")
        monkeypatch.setenv("GENE_DATABASE_URL", "postgresql://env@localhost/test")

        from api.config.models import GeneConfig

        config = GeneConfig(
            openrouter_api_key="constructor-key",
            database_url="postgresql://constructor@localhost/test",
            meta_model="constructor-model",
        )
        assert config.meta_model == "constructor-model"
        assert config.openrouter_api_key == "constructor-key"


class TestOptionalSecrets:
    """Test 7: GeneConfig allows optional secrets (validated at command level)."""

    @pytest.fixture(autouse=True)
    def clean_env(self, monkeypatch):
        """Remove env vars that leak from other test modules."""
        monkeypatch.delenv("GENE_GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GENE_OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("GENE_DATABASE_URL", raising=False)

    def test_openrouter_api_key_defaults_to_none(self):
        """openrouter_api_key defaults to None when not provided."""
        from api.config.models import GeneConfig

        config = GeneConfig(database_url="postgresql://test@localhost/test")
        assert config.openrouter_api_key is None

    def test_database_url_defaults_to_none(self):
        """database_url defaults to None when not provided."""
        from api.config.models import GeneConfig

        config = GeneConfig(openrouter_api_key="test-key", _yaml_file="/dev/null")
        assert config.database_url is None


class TestGenerationConfig:
    """Test 8: GenerationConfig has temperature and max_tokens with defaults."""

    def test_generation_config_defaults(self):
        from api.config.models import GenerationConfig

        gen = GenerationConfig()
        assert gen.temperature == 0.7
        assert gen.max_tokens == 4096

    def test_generation_config_custom(self):
        from api.config.models import GenerationConfig

        gen = GenerationConfig(temperature=0.5, max_tokens=2048)
        assert gen.temperature == 0.5
        assert gen.max_tokens == 2048

    def test_generation_config_optional_fields(self):
        from api.config.models import GenerationConfig

        gen = GenerationConfig()
        assert gen.top_p is None
        assert gen.frequency_penalty is None
        assert gen.presence_penalty is None


class TestLoadPromptConfig:
    """Test 9: load_prompt_config merges per-prompt config.json overrides onto global GeneConfig."""

    def test_merges_prompt_config(self, tmp_path: Path):
        """Per-prompt config.json overrides get merged onto base config."""
        from api.config.loader import load_prompt_config
        from api.config.models import GeneConfig

        base = GeneConfig(
            openrouter_api_key="test-key",
            database_url="postgresql://test@localhost/test",
            target_model="openai/gpt-4o-mini",
            _yaml_file="/dev/null",
        )

        # Create per-prompt config.json
        prompt_dir = tmp_path / "my-prompt"
        prompt_dir.mkdir()
        config_json = {
            "target_model": "anthropic/claude-haiku-3.5",
            "generation": {"temperature": 0.3, "max_tokens": 1024},
        }
        (prompt_dir / "config.json").write_text(json.dumps(config_json))

        merged = load_prompt_config(base, prompt_dir)
        assert merged.target_model == "anthropic/claude-haiku-3.5"
        assert merged.generation.temperature == 0.3
        assert merged.generation.max_tokens == 1024
        # Original values preserved for non-overridden fields
        assert merged.openrouter_api_key == "test-key"
        assert merged.meta_model == "anthropic/claude-sonnet-4"

    def test_no_config_json_returns_base(self, tmp_path: Path):
        """If no config.json exists, return base config unchanged."""
        from api.config.loader import load_prompt_config
        from api.config.models import GeneConfig

        base = GeneConfig(
            openrouter_api_key="test-key",
            database_url="postgresql://test@localhost/test",
        )

        prompt_dir = tmp_path / "no-config-prompt"
        prompt_dir.mkdir()

        result = load_prompt_config(base, prompt_dir)
        assert result.target_model == base.target_model
        assert result.meta_model == base.meta_model


class TestProviderFields:
    """GEM-01: GeneConfig has per-role provider fields."""

    @pytest.fixture(autouse=True)
    def clean_env(self, monkeypatch):
        """Remove env vars that leak from other test modules."""
        monkeypatch.delenv("GENE_GEMINI_API_KEY", raising=False)
        monkeypatch.delenv("GENE_OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("GENE_DATABASE_URL", raising=False)

    def test_config_provider_fields_default_openrouter(self):
        """meta_provider, target_provider, judge_provider all default to 'openrouter'."""
        from api.config.models import GeneConfig

        config = GeneConfig(_yaml_file="/dev/null")
        assert config.meta_provider == "openrouter"
        assert config.target_provider == "openrouter"
        assert config.judge_provider == "openrouter"

    def test_config_gemini_api_key_optional(self):
        """gemini_api_key defaults to None, no validation error."""
        from api.config.models import GeneConfig

        config = GeneConfig(_yaml_file="/dev/null")
        assert config.gemini_api_key is None

    def test_config_provider_per_role(self):
        """Can set meta_provider='gemini' while keeping target_provider='openrouter'."""
        from api.config.models import GeneConfig

        config = GeneConfig(
            meta_provider="gemini", gemini_api_key="test-gemini-key", _yaml_file="/dev/null"
        )
        assert config.meta_provider == "gemini"
        assert config.target_provider == "openrouter"
        assert config.judge_provider == "openrouter"

    def test_config_from_yaml_with_providers(self, tmp_path: Path):
        """YAML with provider fields loads correctly."""
        yaml_content = """\
meta_provider: "gemini"
target_provider: "openrouter"
judge_provider: "gemini"
gemini_api_key: "yaml-gemini-key"
"""
        yaml_file = tmp_path / "gene.yaml"
        yaml_file.write_text(yaml_content)

        from api.config.models import GeneConfig

        config = GeneConfig(_yaml_file=str(yaml_file))
        assert config.meta_provider == "gemini"
        assert config.target_provider == "openrouter"
        assert config.judge_provider == "gemini"
        assert config.gemini_api_key == "yaml-gemini-key"

    def test_config_from_env_gemini_key(self, monkeypatch: pytest.MonkeyPatch):
        """GENE_GEMINI_API_KEY env var populates gemini_api_key."""
        monkeypatch.setenv("GENE_GEMINI_API_KEY", "env-gemini-key")

        from api.config.models import GeneConfig

        config = GeneConfig()
        assert config.gemini_api_key == "env-gemini-key"


class TestConcurrencyLimit:
    """Test 10: concurrency_limit defaults to 10, is configurable."""

    def test_concurrency_limit_default(self):
        from api.config.models import GeneConfig

        config = GeneConfig(
            openrouter_api_key="test-key",
            database_url="postgresql://test@localhost/test",
            _yaml_file="/dev/null",
        )
        assert config.concurrency_limit == 10

    def test_concurrency_limit_configurable(self):
        from api.config.models import GeneConfig

        config = GeneConfig(
            openrouter_api_key="test-key",
            database_url="postgresql://test@localhost/test",
            concurrency_limit=25,
        )
        assert config.concurrency_limit == 25
