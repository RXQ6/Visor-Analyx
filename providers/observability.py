"""Provider-only, bounded in-memory telemetry. No logging or external exporters."""

from __future__ import annotations

import math
import re
from collections import deque
from dataclasses import asdict, dataclass
from threading import Lock
from typing import Any

from .errors import ProviderErrorCategory


_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}\Z")
_REQUEST_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


@dataclass(frozen=True, slots=True)
class ProviderCallMetadata:
    provider_id: str
    model_name: str | None
    latency_ms: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    request_id: str | None = None
    error_category: ProviderErrorCategory | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProviderObservations:
    """Internal snapshots only; never connected to TraceCollector or Session."""

    def __init__(self, *, capacity: int = 64) -> None:
        if type(capacity) is not int or not 1 <= capacity <= 256:
            raise ValueError("provider observation capacity must be between 1 and 256")
        self._records: deque[ProviderCallMetadata] = deque(maxlen=capacity)
        self._lock = Lock()

    def record(self, metadata: ProviderCallMetadata) -> None:
        if not isinstance(metadata, ProviderCallMetadata):
            raise TypeError("provider observations accept only call metadata")
        with self._lock:
            self._records.append(metadata)

    def snapshot(self) -> tuple[ProviderCallMetadata, ...]:
        with self._lock:
            return tuple(self._records)


def _identifier(value: Any, pattern: re.Pattern[str], forbidden: tuple[str, ...]) -> str | None:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        return None
    if "://" in value or value.lower().startswith(("sk-", "bearer", "authorization")):
        return None
    if any(marker and marker in value for marker in forbidden):
        return None
    return value


def _tokens(value: Any) -> int | None:
    # Do not coerce strings/bools or estimate missing vendor usage.
    return value if type(value) is int and 0 <= value <= 2**63 - 1 else None


def make_call_metadata(
    *, model_name: str, latency_ms: float, info: dict[str, Any],
    forbidden: tuple[str, ...],
) -> ProviderCallMetadata:
    """Copy only allowlisted scalars; discard all raw provider/config objects."""
    return ProviderCallMetadata(
        provider_id="openai-compatible",
        model_name=_identifier(model_name, _MODEL_ID, forbidden),
        latency_ms=round(max(0.0, latency_ms), 3) if math.isfinite(latency_ms) else 0.0,
        input_tokens=_tokens(info.get("input_tokens")),
        output_tokens=_tokens(info.get("output_tokens")),
        request_id=_identifier(info.get("request_id"), _REQUEST_ID, forbidden),
        error_category=info.get("error_category"),
        error_code=info.get("error_code"),
    )
