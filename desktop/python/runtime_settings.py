"""Desktop composition metadata only; no credential persistence or new policy."""
from __future__ import annotations

import json
import re
import shutil
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from mcp_adapter import MCPHost
from mcp_adapter.readonly_filesystem import FILESYSTEM_TOOL_NAME, attach_readonly_filesystem
from providers import MissingAPIKeyError, ProviderConfig, ProviderConfigError, create_provider
from tools import build_default_registry

WORKER_SETTINGS_ENV = "DESKTOP_RUNTIME_SETTINGS"
ROOT_SUMMARY = "公开测试目录（tests/fixtures/mcp-readonly）；仅文件/目录元数据"


class SettingsError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "message": str(self)}


def default_settings() -> dict[str, Any]:
    return {"provider": {"provider_id": "deterministic", "model_name": None,
                         "endpoint": None, "api_key_env": None}, "mcp": {"enabled": False}}


def _exact(value: Any, keys: set[str]) -> None:
    if not isinstance(value, dict) or set(value) != keys:
        raise SettingsError("settings_invalid", "配置包含不支持的字段。")


def validate_settings(value: Any) -> dict[str, Any]:
    _exact(value, {"provider", "mcp"})
    provider, mcp = value["provider"], value["mcp"]
    _exact(provider, {"provider_id", "model_name", "endpoint", "api_key_env"})
    _exact(mcp, {"enabled"})
    if type(mcp["enabled"]) is not bool:
        raise SettingsError("settings_invalid", "只读 MCP 开关无效。")
    if provider["provider_id"] not in ("deterministic", "openai-compatible"):
        raise SettingsError("settings_invalid", "当前仅支持本地测试模式和 OpenAI-compatible。")
    if provider["provider_id"] == "deterministic" and any(provider[field] is not None for field in ("model_name", "endpoint", "api_key_env")):
        raise SettingsError("settings_invalid", "本地模式不接受外部模型或凭据配置。")
    result = default_settings()
    result["provider"]["provider_id"] = provider["provider_id"]
    result["mcp"]["enabled"] = mcp["enabled"]
    for field, limit in (("model_name", 128), ("endpoint", 1024), ("api_key_env", 128)):
        item = provider[field]
        if item is not None and (not isinstance(item, str) or len(item) > limit or item != item.strip()):
            raise SettingsError("settings_invalid", "模型配置格式无效。")
        if isinstance(item, str) and re.search(r"(?i)(?:^sk-|^AIza|^Bearer\s)", item):
            raise SettingsError("settings_invalid", "此页面只接受凭据引用，不接受密钥。")
        result["provider"][field] = item or None
    if result["provider"]["model_name"] is not None and not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}", result["provider"]["model_name"]
    ):
        raise SettingsError("settings_invalid", "模型名称格式无效。")
    if result["provider"]["api_key_env"] is not None and not re.fullmatch(
        r"[A-Za-z_][A-Za-z0-9_]{0,127}", result["provider"]["api_key_env"]
    ):
        raise SettingsError("settings_invalid", "请输入环境变量名，不是 API Key。")
    endpoint = result["provider"]["endpoint"]
    if endpoint is not None:
        valid = False
        try:
            parts = urlsplit(endpoint)
            valid = bool(parts.hostname) and (parts.scheme == "https" or
                (parts.scheme == "http" and parts.hostname in ("localhost", "127.0.0.1", "::1")))
            valid = valid and parts.username is None and parts.password is None and not parts.query and not parts.fragment
            valid = valid and not any(c.isspace() for c in endpoint)
            _ = parts.port
        except ValueError:
            pass
        if not valid:
            raise SettingsError("settings_invalid", "地址须为 HTTPS 或本机 HTTP，且不含凭据、查询参数或片段。")
    if provider["provider_id"] == "openai-compatible" and any(
        result["provider"][field] is None for field in ("model_name", "endpoint", "api_key_env")
    ):
        raise SettingsError("settings_missing_fields", "请填写模型名称、服务地址和 API Key 环境变量名。")
    return result


def provider_config(settings: dict[str, Any]) -> ProviderConfig:
    return ProviderConfig(**settings["provider"])


def host_node() -> str:
    root = Path(__file__).resolve().parents[2]
    packaged = root / "bin" / "node.exe"
    if (root / "python-runtime").is_dir():
        # Installed resources must never recover a missing private executable
        # by picking up an unrelated global Node from the host PATH.
        return str(packaged)
    node = str(packaged) if packaged.is_file() else shutil.which("node")
    if not node:
        raise SettingsError("settings_mcp_unavailable", "只读文件服务不可用，请检查本机 MCP 依赖。")
    return node


@contextmanager
def mcp_connection(registry: Any, enabled: bool):
    if not enabled:
        yield None
        return
    host = MCPHost(registry)
    try:
        try:
            report = attach_readonly_filesystem(host, node_executable=host_node())
            if not report.ok or report.registered_tools != (FILESYSTEM_TOOL_NAME,):
                raise SettingsError("settings_mcp_unavailable", "只读文件服务不可用，请检查本机 MCP 依赖。")
        except SettingsError:
            raise
        except Exception:
            raise SettingsError("settings_mcp_unavailable", "只读文件服务不可用，请检查本机 MCP 依赖。") from None
        yield host
    finally:
        host.close()


def inspect_settings(settings: dict[str, Any]) -> dict[str, Any]:
    """Check configuration/credential availability and MCP discovery; no model call."""
    settings = validate_settings(settings)
    issue = None
    credentials = "not_required" if settings["provider"]["provider_id"] == "deterministic" else "available"
    try:
        create_provider(provider_config(settings))
    except MissingAPIKeyError:
        credentials = "missing"
        issue = {"code": "settings_missing_credentials", "message": "所选环境变量中没有可用凭据。请在系统环境中设置后重启应用。"}
    except ProviderConfigError:
        # A provider can reject credential material hidden in metadata. Never
        # return that configuration to Renderer, including during disk restore.
        raise SettingsError("settings_invalid", "模型配置无法使用，请检查设置。") from None
    registered = []
    mcp_status = "disabled"
    if settings["mcp"]["enabled"]:
        try:
            with mcp_connection(build_default_registry(), True):
                registered = [FILESYSTEM_TOOL_NAME]
                mcp_status = "ready"
        except SettingsError as error:
            mcp_status = "unavailable"
            issue = issue or error.to_dict()
    return {"config": settings, "ready": issue is None, "issue": issue,
            "credentials": credentials,
            "mcp": {"enabled": settings["mcp"]["enabled"], "read_only": True,
                    "root_summary": ROOT_SUMMARY, "registered_tools": registered, "status": mcp_status}}


def decode_worker_settings(encoded: str) -> dict[str, Any]:
    if len(encoded) > 8192:
        raise SettingsError("settings_invalid", "配置长度无效。")
    try:
        value = json.loads(encoded)
    except ValueError:
        raise SettingsError("settings_invalid", "配置格式无效。") from None
    return validate_settings(value)
