"""Exception hierarchy for Helix."""


class GenePrompterError(Exception):
    """Base exception for all Helix errors."""

    pass


class ConfigError(GenePrompterError):
    """Configuration loading or validation failure."""

    pass


class PromptNotFoundError(GenePrompterError):
    """Prompt ID not found in registry."""

    pass


class PromptAlreadyExistsError(GenePrompterError):
    """Prompt ID already exists in registry."""

    pass


class RetryableError(GenePrompterError):
    """Retryable HTTP error (429, 5xx) from LLM gateway."""

    def __init__(self, status_code: int = 0, response_text: str = "", *args, **kwargs):
        self.status_code = status_code
        self.response_text = response_text
        super().__init__(f"HTTP {status_code}: {response_text}", *args, **kwargs)


class GatewayError(GenePrompterError):
    """Non-retryable gateway error."""

    pass


class StorageError(GenePrompterError):
    """Database or git storage error."""

    pass


class BudgetExhaustedError(GenePrompterError):
    """Evolution budget cap exceeded."""

    pass
