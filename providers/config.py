"""In-memory provider configuration containing credential references only."""

from __future__ import annotations

import os
import math
from collections.abc import Mapping
from dataclasses import dataclass

DEFAULT_PROVIDER_TIMEOUT_SECONDS = 30.0
MAX_PROVIDER_TIMEOUT_SECONDS = 120.0


def validate_provider_timeout(value: float) -> None:
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or not 0 < value <= MAX_PROVIDER_TIMEOUT_SECONDS):
        raise ProviderConfigError("provider timeout_seconds must be greater than 0 and at most 120")


# Reserved identifiers describe future adapters, not implemented providers.
RESERVED_PROVIDER_IDS = (
    "openai",
    "anthropic",
    "gemini",
    "local",
)


class ProviderConfigError(ValueError):
    """Safe structured configuration error without configuration values."""

    code = "invalid_provider_config"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, repr=False)
class ProviderConfig:
    """Composition-only config; never contains an API key value."""

    provider_id: str = "deterministic"
    model_name: str | None = None
    endpoint: str | None = None
    api_key_env: str | None = None
    timeout_seconds: float = DEFAULT_PROVIDER_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, str) or not self.provider_id.strip():
            raise ProviderConfigError("provider_id must be a non-empty string")
        for field_name in ("model_name", "endpoint", "api_key_env"):
            value = getattr(self, field_name)
            if value is not None and not isinstance(value, str):
                raise ProviderConfigError(f"{field_name} must be a string or None")
        validate_provider_timeout(self.timeout_seconds)


def load_provider_config(environ: Mapping[str, str] | None = None) -> ProviderConfig:
    """Read only selection metadata; credentials remain the provider's responsibility.

    An absent selector defaults to deterministic. Optional real-provider fields
    never enable a provider implicitly. An explicit empty/unknown selector fails
    validation/composition rather than falling back. No files are loaded.
    """
    source = os.environ if environ is None else environ
    provider_id = source.get("DATA_AGENT_PROVIDER_ID", "deterministic")
    if provider_id == "deterministic":
        return ProviderConfig()
    timeout_seconds = None
    try:
        timeout_seconds = float(source.get("DATA_AGENT_PROVIDER_TIMEOUT_SECONDS", "30"))
    except (TypeError, ValueError, OverflowError):
        pass
    # Raise outside the parser exception handler; never chain a config value.
    if timeout_seconds is None:
        raise ProviderConfigError("provider timeout_seconds must be a number")
    return ProviderConfig(
        provider_id=provider_id,
        model_name=source.get("DATA_AGENT_MODEL_NAME"),
        endpoint=source.get("DATA_AGENT_PROVIDER_ENDPOINT"),
        api_key_env=source.get("DATA_AGENT_API_KEY_ENV"),
        timeout_seconds=timeout_seconds,
    )
