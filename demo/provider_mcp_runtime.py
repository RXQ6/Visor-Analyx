"""Explicit Provider + read-only MCP composition, outside the default Desktop.

There is no new execution loop, provider mode, protocol or environment loader.
Tests may supply a host-owned scripted factory. Normal explicit composition
uses the existing ProviderConfig and create_provider without changing either.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from agent import AgentLoop
from agent.state import AgentState
from mcp_adapter import MCPHost
from mcp_adapter.readonly_filesystem import FILESYSTEM_TOOL_NAME, attach_readonly_filesystem
from observability import TraceCollector
from providers import ModelProvider, ProviderConfig, create_provider
from tools import build_default_registry


class ProviderMCPRuntimeError(RuntimeError):
    """Composition failed; do not silently run without the requested MCP tool."""

    def __init__(self, code: str) -> None:
        super().__init__("Provider/MCP Runtime composition failed")
        self.code = code


class ProviderMCPRuntime:
    """Own one explicitly configured provider, Registry, AgentLoop and MCP Host."""

    def __init__(
        self,
        *,
        node_executable: str | Path,
        provider_config: ProviderConfig | None = None,
        provider_factory: Callable[[ProviderConfig | None], ModelProvider] | None = None,
        mcp_call_timeout_seconds: float = 5.0,
        max_iter: int = 6,
    ) -> None:
        # No ambient provider selection or credentials are read by this module.
        # Factory failures propagate before an external MCP process is started.
        factory = create_provider if provider_factory is None else provider_factory
        self.provider = factory(provider_config)
        self.registry = build_default_registry()
        self.host = MCPHost(self.registry)
        self._closed = False
        try:
            report = attach_readonly_filesystem(
                self.host,
                node_executable=node_executable,
                call_timeout_seconds=mcp_call_timeout_seconds,
            )
            if not report.ok:
                raise ProviderMCPRuntimeError(report.error["code"])
            if report.registered_tools != (FILESYSTEM_TOOL_NAME,):
                raise ProviderMCPRuntimeError("mcp_required_tool_missing")
            self.agent = AgentLoop(self.provider, self.registry, max_iter=max_iter)
        except BaseException:
            self.close()
            raise

    def run(self, question: str, *, trace_collector: TraceCollector | None = None) -> AgentState:
        if self._closed:
            raise RuntimeError("Provider/MCP Runtime is closed")
        return self.agent.run(question, trace_collector=trace_collector)

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.host.close()

    def __enter__(self) -> ProviderMCPRuntime:
        return self

    def __exit__(self, *_exception: object) -> None:
        self.close()
