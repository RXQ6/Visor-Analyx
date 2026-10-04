"""Explicit provider composition from an in-memory configuration."""

from __future__ import annotations

from .config import ProviderConfig, ProviderConfigError
from .contracts import ModelProvider
from .deterministic import DeterministicModelProvider
from .openai_compatible import OpenAICompatibleProvider


class UnknownProviderError(ProviderConfigError):
    """Raised for any unimplemented provider, including reserved identifiers."""

    code = "unsupported_provider"


def create_provider(
    config: ProviderConfig | str | None = None, *, name: str | None = None
) -> ModelProvider:
    """Create only the configured provider, retaining legacy string/name calls."""
    if name is not None:
        if config is not None:
            raise ProviderConfigError("config and legacy name cannot both be supplied")
        config = ProviderConfig(provider_id=name)
    if config is None:
        config = ProviderConfig()
    elif isinstance(config, str):
        config = ProviderConfig(provider_id=config)
    elif not isinstance(config, ProviderConfig):
        raise ProviderConfigError("config must be a ProviderConfig or provider ID")
    if config.provider_id == "deterministic":
        return DeterministicModelProvider()
    if config.provider_id == "openai-compatible":
        return OpenAICompatibleProvider(config)
    raise UnknownProviderError("unsupported model provider; no adapter is implemented")
