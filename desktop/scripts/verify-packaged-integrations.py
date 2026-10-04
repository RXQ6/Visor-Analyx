"""Offline acceptance against installed resources, using only private dependencies."""
from __future__ import annotations

import argparse
import builtins
import json
import os
import sys
import tempfile
from contextlib import closing
from pathlib import Path
from unittest.mock import patch


def verify(resources: Path) -> dict:
    assert Path(sys.executable).resolve() == (resources / "python-runtime/python.exe").resolve()
    assert not any(".packaging-deps" in entry for entry in sys.path)
    sys.path.insert(0, str(resources))
    from desktop.python import runtime_settings
    from providers import create_provider, DeterministicModelProvider, OpenAICompatibleProvider, ProviderConfig
    from mcp_adapter import MCPHost
    from mcp_adapter import readonly_filesystem as filesystem
    from tools import build_default_registry
    import mcp

    assert Path(mcp.__file__).resolve().is_relative_to(resources / "python-runtime")
    assert isinstance(create_provider(), DeterministicModelProvider)
    assert runtime_settings.inspect_settings(runtime_settings.default_settings())["ready"]
    config = runtime_settings.default_settings()
    config["mcp"]["enabled"] = True
    assert runtime_settings.inspect_settings(config)["mcp"]["status"] == "ready"
    node = resources / "bin/node.exe"
    assert Path(runtime_settings.host_node()) == node
    registry = build_default_registry()
    with closing(MCPHost(registry)) as host:
        report = filesystem.attach_readonly_filesystem(host, node_executable=node)
        assert report.ok and report.registered_tools == (filesystem.FILESYSTEM_TOOL_NAME,)
        schema = next(item["function"] for item in registry.tool_schemas()
                      if item["function"]["name"] == filesystem.FILESYSTEM_TOOL_NAME)
        assert schema["parameters"]["required"] == ["path"]
        result = registry.execute(filesystem.FILESYSTEM_TOOL_NAME, {"path": "metadata.txt"})
        assert result["ok"], result["error"]
        expected_size = (filesystem.FILESYSTEM_ALLOWED_ROOT / "metadata.txt").stat().st_size
        assert f"size: {expected_size}" in result["data"]["structuredContent"]["content"]
        denied = registry.execute(filesystem.FILESYSTEM_TOOL_NAME, {"path": str(resources.parent)})
        assert not denied["ok"]

    # Synthetic, process-only credential verifies factory availability without
    # reading a real credential or sending a model request.
    with patch.dict(os.environ, {"PHASE29_SYNTHETIC_KEY": "synthetic-local-acceptance"}):
        provider = create_provider(ProviderConfig(provider_id="openai-compatible", model_name="acceptance-model",
            endpoint="https://acceptance.invalid/v1/chat/completions", api_key_env="PHASE29_SYNTHETIC_KEY"))
        assert isinstance(provider, OpenAICompatibleProvider)

    with tempfile.TemporaryDirectory() as missing:
        isolated = Path(missing)
        (isolated / "python-runtime").mkdir()
        with patch.object(runtime_settings, "__file__", str(isolated / "desktop/python/runtime_settings.py")):
            with patch.object(runtime_settings.shutil, "which", side_effect=AssertionError("global Node lookup")):
                assert runtime_settings.host_node() == str(isolated / "bin/node.exe")
            unavailable = runtime_settings.inspect_settings(config)
            assert not unavailable["ready"] and unavailable["issue"]["code"] == "settings_mcp_unavailable"
        with patch.object(filesystem, "FILESYSTEM_PACKAGE_ROOT", Path(missing)):
            with closing(MCPHost(build_default_registry())) as host:
                failure = filesystem.attach_readonly_filesystem(host, node_executable=node)
                assert not failure.ok and failure.error["code"] == "mcp_dependency_missing"
            unavailable = runtime_settings.inspect_settings(config)
            assert not unavailable["ready"]
            assert unavailable["issue"]["code"] == "settings_mcp_unavailable"
        with closing(MCPHost(build_default_registry())) as host:
            failure = filesystem.attach_readonly_filesystem(host, node_executable=Path(missing) / "node.exe")
            assert not failure.ok and failure.error["code"] == "mcp_server_unavailable"
    original_import = builtins.__import__
    def without_sdk(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp."):
            raise ImportError("optional SDK unavailable")
        return original_import(name, *args, **kwargs)
    with patch("builtins.__import__", side_effect=without_sdk):
        unavailable = runtime_settings.inspect_settings(config)
        assert not unavailable["ready"] and unavailable["issue"]["code"] == "settings_mcp_unavailable"
    return {"status": "PASS", "private_python_node_sdk": True, "default_provider": "deterministic",
            "compatible_factory_only_no_model_request": True, "list_tools_schema_call_tool": "PASS",
            "tool_result_size": expected_size, "read_only_scope_rejected": True,
            "missing_dependencies_structured": True, "external_model_requests": 0}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--resources", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.resources.resolve()), ensure_ascii=True))
