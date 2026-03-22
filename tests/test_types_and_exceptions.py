"""Tests for shared types (ModelRole, LLMResponse, CostRecord) and exception hierarchy."""

from datetime import datetime, timezone


class TestModelRole:
    """Test 1: ModelRole enum has META, TARGET, JUDGE values."""

    def test_model_role_has_meta(self):
        from api.types import ModelRole

        assert ModelRole.META == "meta"

    def test_model_role_has_target(self):
        from api.types import ModelRole

        assert ModelRole.TARGET == "target"

    def test_model_role_has_judge(self):
        from api.types import ModelRole

        assert ModelRole.JUDGE == "judge"

    def test_model_role_is_str_enum(self):
        from api.types import ModelRole

        assert isinstance(ModelRole.META, str)


class TestLLMResponse:
    """Test 2: LLMResponse accepts all required fields."""

    def test_llm_response_all_fields(self):
        from api.types import LLMResponse, ModelRole

        response = LLMResponse(
            content="Hello, world!",
            tool_calls=None,
            model_used="anthropic/claude-sonnet-4",
            role=ModelRole.TARGET,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.001,
            generation_id="gen-123",
            timestamp=datetime.now(timezone.utc),
            finish_reason="stop",
        )
        assert response.content == "Hello, world!"
        assert response.model_used == "anthropic/claude-sonnet-4"
        assert response.role == ModelRole.TARGET
        assert response.input_tokens == 100
        assert response.output_tokens == 50
        assert response.cost_usd == 0.001
        assert response.generation_id == "gen-123"

    def test_llm_response_content_can_be_none(self):
        """Test 4: LLMResponse.content can be None (for tool-only responses)."""
        from api.types import LLMResponse, ModelRole

        response = LLMResponse(
            content=None,
            tool_calls=[{"type": "function", "function": {"name": "get_weather"}}],
            model_used="openai/gpt-4o-mini",
            role=ModelRole.META,
            input_tokens=200,
            output_tokens=30,
            cost_usd=0.0005,
            generation_id=None,
            timestamp=datetime.now(timezone.utc),
        )
        assert response.content is None
        assert response.tool_calls is not None
        assert len(response.tool_calls) == 1


class TestCostRecord:
    """Test 3: CostRecord accepts all required fields."""

    def test_cost_record_all_fields(self):
        from api.types import CostRecord

        record = CostRecord(
            total_cost_usd=0.05,
            input_tokens=1000,
            output_tokens=500,
            provider="openai",
            model="gpt-4o-mini",
            latency_ms=1200.5,
            generation_time_ms=800.3,
        )
        assert record.total_cost_usd == 0.05
        assert record.input_tokens == 1000
        assert record.output_tokens == 500
        assert record.provider == "openai"
        assert record.model == "gpt-4o-mini"
        assert record.latency_ms == 1200.5
        assert record.generation_time_ms == 800.3

    def test_cost_record_optional_fields_default_none(self):
        from api.types import CostRecord

        record = CostRecord(
            total_cost_usd=None,
            input_tokens=100,
            output_tokens=50,
        )
        assert record.total_cost_usd is None
        assert record.provider is None
        assert record.model is None
        assert record.latency_ms is None
        assert record.generation_time_ms is None


class TestExceptionHierarchy:
    """Test 5: Exception hierarchy."""

    def test_helix_error_is_base(self):
        from api.exceptions import GenePrompterError

        assert issubclass(GenePrompterError, Exception)

    def test_config_error_inherits_from_base(self):
        from api.exceptions import ConfigError, GenePrompterError

        assert issubclass(ConfigError, GenePrompterError)

    def test_prompt_not_found_error_inherits_from_base(self):
        from api.exceptions import GenePrompterError, PromptNotFoundError

        assert issubclass(PromptNotFoundError, GenePrompterError)

    def test_prompt_already_exists_error_inherits_from_base(self):
        from api.exceptions import GenePrompterError, PromptAlreadyExistsError

        assert issubclass(PromptAlreadyExistsError, GenePrompterError)

    def test_retryable_error_inherits_from_base(self):
        from api.exceptions import GenePrompterError, RetryableError

        assert issubclass(RetryableError, GenePrompterError)

    def test_retryable_error_has_status_code_and_response_text(self):
        from api.exceptions import RetryableError

        err = RetryableError(status_code=429, response_text="Rate limited")
        assert err.status_code == 429
        assert err.response_text == "Rate limited"

    def test_gateway_error_inherits_from_base(self):
        from api.exceptions import GatewayError, GenePrompterError

        assert issubclass(GatewayError, GenePrompterError)

    def test_storage_error_inherits_from_base(self):
        from api.exceptions import GenePrompterError, StorageError

        assert issubclass(StorageError, GenePrompterError)

    def test_all_exceptions_catchable_by_base(self):
        from api.exceptions import (
            ConfigError,
            GatewayError,
            GenePrompterError,
            PromptAlreadyExistsError,
            PromptNotFoundError,
            RetryableError,
            StorageError,
        )

        for exc_cls in [
            ConfigError,
            PromptNotFoundError,
            PromptAlreadyExistsError,
            RetryableError,
            GatewayError,
            StorageError,
        ]:
            try:
                raise exc_cls(f"Test {exc_cls.__name__}")
            except GenePrompterError:
                pass  # Expected -- caught by base class
