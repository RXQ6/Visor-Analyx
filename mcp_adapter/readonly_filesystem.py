"""Explicit, fixture-scoped composition for the first external MCP server.

This does not change the default Registry or Desktop composition. The host owns
the executable; neither model input nor a Settings value can choose a command,
directory, environment or permission set.
"""

from __future__ import annotations

import json
from pathlib import Path

from .adapter import MCPRegistrationReport
from .contracts import MCPRemoteError
from .host import MCPHost
from .sdk_stdio_client import MCPStdioClient


FILESYSTEM_SERVER_ID = "filesystem"
FILESYSTEM_SERVER_VERSION = "2026.8.31"
FILESYSTEM_TOOL_NAME = "mcp_filesystem__get_file_info"
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
FILESYSTEM_ALLOWED_ROOT = _PROJECT_ROOT / "tests" / "fixtures" / "mcp-readonly"
FILESYSTEM_PACKAGE_ROOT = (
    _PROJECT_ROOT / "integrations" / "mcp-filesystem" / "node_modules"
    / "@modelcontextprotocol" / "server-filesystem"
)


def attach_readonly_filesystem(
    host: MCPHost,
    *,
    node_executable: str | Path,
    startup_timeout_seconds: float = 10.0,
    call_timeout_seconds: float = 5.0,
    max_result_bytes: int = 4 * 1024,
) -> MCPRegistrationReport:
    """Start the pinned server and grant only get_file_info via the existing Host.

    The optional npm dependency must already be installed. No npx, shell, network
    install, environment file, credential lookup or broader root is used here.
    Failure is explicit and the original Registry remains usable.
    """

    node = Path(node_executable)
    if not node.is_absolute() or node.name.lower() not in {"node", "node.exe"}:
        return _failure("mcp_configuration_error", "A host-owned Node executable is required")
    if not node.is_file():
        return _failure("mcp_server_unavailable", "The MCP Node executable is unavailable")
    root = FILESYSTEM_ALLOWED_ROOT
    if not root.is_dir() or root.resolve() != root:
        return _failure("mcp_configuration_error", "The fixed MCP fixture directory is unavailable")
    entrypoint = FILESYSTEM_PACKAGE_ROOT / "dist" / "index.js"
    try:
        manifest = json.loads((FILESYSTEM_PACKAGE_ROOT / "package.json").read_text("utf-8"))
        if manifest.get("version") != FILESYSTEM_SERVER_VERSION or not entrypoint.is_file():
            return _failure("mcp_dependency_missing", "Install the pinned optional Filesystem MCP dependency")
    except (OSError, ValueError, AttributeError):
        return _failure("mcp_dependency_missing", "Install the pinned optional Filesystem MCP dependency")

    try:
        client = MCPStdioClient(
            str(node),
            args=[str(entrypoint), str(root)],
            # SDK inherits its own small OS allowlist. Do not copy os.environ:
            # API keys, provider config and NODE_OPTIONS must not reach Node.
            env={},
            cwd=root,
            startup_timeout_seconds=startup_timeout_seconds,
        )
    except MCPRemoteError:
        return _failure("mcp_server_unavailable", "The Filesystem MCP server could not start")
    try:
        report = host.attach_server(
            client,
            server_id=FILESYSTEM_SERVER_ID,
            allowed_tools={"get_file_info"},
            tool_policies={"get_file_info": "mcp_read"},
            call_timeout_seconds=call_timeout_seconds,
            max_result_bytes=max_result_bytes,
        )
    except BaseException:
        client.close()
        raise
    if not report.ok:
        client.close()
    return report


def _failure(code: str, message: str) -> MCPRegistrationReport:
    return MCPRegistrationReport(
        ok=False,
        server_id=FILESYSTEM_SERVER_ID,
        registered_tools=(),
        error={"code": code, "message": message},
    )
