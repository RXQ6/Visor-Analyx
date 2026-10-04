"""Fixed, structured provider errors safe for Runtime and Session consumers."""

from .config import ProviderConfigError
from typing import Literal


ProviderErrorCategory = Literal[
    "auth_error", "rate_limited", "timeout", "network_error",
    "invalid_response", "provider_unavailable",
]


class MissingAPIKeyError(ProviderConfigError):
    code = "missing_api_key"

    def __init__(self) -> None:
        super().__init__("provider API key environment variable is missing or invalid")


class ProviderError(RuntimeError):
    code = "provider_error"
    message = "model provider request failed"
    category: ProviderErrorCategory | None = "provider_unavailable"

    def __init__(self) -> None:
        super().__init__(self.message)

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


class ProviderTimeoutError(ProviderError):
    category = "timeout"
    code = "provider_timeout"
    message = "model provider request timed out"


class ProviderAuthenticationError(ProviderError):
    category = "auth_error"
    code = "provider_auth_error"
    message = "model provider authentication failed"


class ProviderNetworkError(ProviderError):
    category = "network_error"
    code = "provider_network_error"
    message = "model provider connection failed"


class ProviderHTTPError(ProviderError):
    category = "invalid_response"
    code = "provider_http_error"
    message = "model provider returned an unsuccessful HTTP status"


class ProviderRateLimitedError(ProviderHTTPError):
    category = "rate_limited"
    code = "provider_rate_limited"
    message = "model provider rate limit or quota was exceeded"


class ProviderUnavailableError(ProviderHTTPError):
    category = "provider_unavailable"
    code = "provider_unavailable"
    message = "model provider is temporarily unavailable"


class ProviderInvalidResponseError(ProviderError):
    category = "invalid_response"
    code = "provider_invalid_response"
    message = "model provider returned an invalid or unsupported response"


class ProviderRequestError(ProviderError):
    # Local preflight validation is not a remote service failure.
    category = None
    code = "provider_invalid_request"
    message = "model provider input is invalid or contains credential material"


def classify_provider_error(error: Exception) -> ProviderErrorCategory | None:
    """Canonical service categories; preserve existing public error envelopes."""
    if isinstance(error, MissingAPIKeyError):
        return "auth_error"
    if isinstance(error, ProviderError):
        return error.category
    return None
