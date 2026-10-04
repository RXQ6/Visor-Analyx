"""Model provider contracts and built-in implementations."""

from .config import (
    DEFAULT_PROVIDER_TIMEOUT_SECONDS, MAX_PROVIDER_TIMEOUT_SECONDS,
    ProviderConfig, ProviderConfigError, RESERVED_PROVIDER_IDS, load_provider_config,
)
from .contracts import ModelDecision, ModelMessage, ModelProvider, ToolSchema
from .deterministic import DeterministicModelProvider
from .factory import UnknownProviderError, create_provider
from .openai_compatible import OpenAICompatibleProvider
from .errors import (
    MissingAPIKeyError, ProviderError, ProviderAuthenticationError,
    ProviderHTTPError, ProviderInvalidResponseError, ProviderNetworkError,
    ProviderRequestError, ProviderTimeoutError,
    ProviderErrorCategory, ProviderRateLimitedError, ProviderUnavailableError,
    classify_provider_error,
)
from .observability import ProviderCallMetadata, ProviderObservations

__all__ = [
    "DeterministicModelProvider",
    "DEFAULT_PROVIDER_TIMEOUT_SECONDS",
    "MAX_PROVIDER_TIMEOUT_SECONDS",
    "ModelDecision",
    "ModelMessage",
    "ModelProvider",
    "OpenAICompatibleProvider",
    "MissingAPIKeyError",
    "ProviderError",
    "ProviderErrorCategory",
    "ProviderCallMetadata",
    "ProviderObservations",
    "ProviderAuthenticationError",
    "ProviderHTTPError",
    "ProviderInvalidResponseError",
    "ProviderNetworkError",
    "ProviderRequestError",
    "ProviderRateLimitedError",
    "ProviderTimeoutError",
    "ProviderUnavailableError",
    "ProviderConfig",
    "ProviderConfigError",
    "RESERVED_PROVIDER_IDS",
    "ToolSchema",
    "UnknownProviderError",
    "create_provider",
    "load_provider_config",
    "classify_provider_error",
]
