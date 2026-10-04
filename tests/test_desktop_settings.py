from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch

from desktop.python import runtime_bridge as bridge
from desktop.python import runtime_settings as settings
from mcp_adapter.readonly_filesystem import FILESYSTEM_TOOL_NAME
from providers import DeterministicModelProvider, OpenAICompatibleProvider, create_provider
from tools import build_default_registry


KEY_ENV = "PHASE28_TEST_API_KEY"
KEY = "synthetic-phase28-no-real-key"


def external():
    return {"provider": {"provider_id": "openai-compatible", "model_name": "phase28-model",
                         "endpoint": "https://phase28.invalid/v1", "api_key_env": KEY_ENV},
            "mcp": {"enabled": False}}


class DesktopSettingsTests(unittest.TestCase):
    def test_default_deterministic_does_not_read_credentials(self):
        with patch("providers.openai_compatible.os.environ.get", side_effect=AssertionError("key read")):
            snapshot = settings.inspect_settings(settings.default_settings())
        self.assertTrue(snapshot["ready"])
        self.assertEqual(snapshot["credentials"], "not_required")
        self.assertIsInstance(create_provider(settings.provider_config(snapshot["config"])), DeterministicModelProvider)

    def test_explicit_compatible_uses_existing_factory_without_network(self):
        with patch.dict(os.environ, {KEY_ENV: KEY}), patch("providers.openai_compatible.build_opener") as opener:
            snapshot = settings.inspect_settings(external())
            self.assertIsInstance(create_provider(settings.provider_config(external())), OpenAICompatibleProvider)
            opener.return_value.open.assert_not_called()
        self.assertTrue(snapshot["ready"])
        self.assertEqual(snapshot["credentials"], "available")
        self.assertNotIn(KEY, json.dumps(snapshot))

    def test_missing_configuration_fails(self):
        for field in ("model_name", "endpoint", "api_key_env"):
            config = external()
            config["provider"][field] = None
            with self.subTest(field=field), self.assertRaises(settings.SettingsError) as failure:
                settings.inspect_settings(config)
            self.assertEqual(failure.exception.code, "settings_missing_fields")

    def test_missing_credentials_are_safe_and_no_fallback(self):
        with patch.dict(os.environ, {KEY_ENV: ""}), patch("providers.factory.DeterministicModelProvider") as fallback:
            snapshot = settings.inspect_settings(external())
        fallback.assert_not_called()
        self.assertFalse(snapshot["ready"])
        self.assertEqual(snapshot["credentials"], "missing")
        self.assertNotIn(KEY_ENV, snapshot["issue"]["message"])

    def test_unknown_provider_is_rejected(self):
        config = settings.default_settings()
        config["provider"]["provider_id"] = "anthropic"
        with self.assertRaises(settings.SettingsError):
            settings.validate_settings(config)

    def test_key_values_and_credential_endpoints_are_rejected(self):
        candidates = []
        for field, value in (("api_key", KEY), ("api_key_env", "sk-private"),
                             ("model_name", "sk-private"), ("endpoint", "https://user:secret@phase28.invalid/v1"),
                             ("endpoint", "https://phase28.invalid/v1?api_key=secret")):
            config = external()
            config["provider"][field] = value
            candidates.append(config)
        for config in candidates:
            with self.subTest(config_keys=list(config["provider"])), self.assertRaises(settings.SettingsError):
                settings.validate_settings(config)

    def test_mcp_disabled_never_starts_a_server(self):
        with patch.object(settings, "attach_readonly_filesystem", side_effect=AssertionError("unexpected MCP")):
            snapshot = settings.inspect_settings(settings.default_settings())
            with settings.mcp_connection(build_default_registry(), False) as host:
                self.assertIsNone(host)
        self.assertEqual(snapshot["mcp"]["registered_tools"], [])
        self.assertEqual(snapshot["mcp"]["status"], "disabled")

    def test_enabled_mcp_registers_only_the_original_readonly_tool(self):
        config = settings.default_settings()
        config["mcp"]["enabled"] = True
        snapshot = settings.inspect_settings(config)
        self.assertTrue(snapshot["ready"], snapshot["issue"])
        self.assertEqual(snapshot["mcp"]["registered_tools"], [FILESYSTEM_TOOL_NAME])
        registry = build_default_registry()
        with settings.mcp_connection(registry, True):
            result = registry.execute(FILESYSTEM_TOOL_NAME, {"path": "metadata.txt"})
            self.assertTrue(result["ok"])
            self.assertIn("size: 78", result["data"]["content"][0]["text"])
            self.assertNotIn("mcp_filesystem__write_file", [item["function"]["name"] for item in registry.tool_schemas()])

    def test_mcp_unavailable_is_explicit(self):
        config = settings.default_settings()
        config["mcp"]["enabled"] = True
        with patch.object(settings, "host_node", side_effect=settings.SettingsError("settings_mcp_unavailable", "服务不可用。")):
            snapshot = settings.inspect_settings(config)
        self.assertFalse(snapshot["ready"])
        self.assertEqual(snapshot["mcp"]["status"], "unavailable")
        self.assertEqual(snapshot["mcp"]["registered_tools"], [])

    def test_renderer_cannot_choose_root_command_permissions_or_tools(self):
        for field, value in (("root", "D:/"), ("allowed_tools", ["write_file"]),
                             ("command", "powershell"), ("read_only", False), ("env", {"KEY": KEY})):
            config = settings.default_settings()
            config["mcp"][field] = value
            with self.subTest(field=field), self.assertRaises(settings.SettingsError):
                settings.validate_settings(config)

    def test_worker_snapshot_codec_is_strict_and_has_no_key_value(self):
        encoded = json.dumps(external())
        self.assertEqual(settings.decode_worker_settings(encoded), external())
        self.assertNotIn(KEY, encoded)
        with self.assertRaises(settings.SettingsError):
            settings.decode_worker_settings('{"provider":{},"mcp":{}}')

    def test_credential_material_hidden_in_metadata_is_never_returned(self):
        config = external()
        config["provider"]["model_name"] = KEY
        with patch.dict(os.environ, {KEY_ENV: KEY}), self.assertRaises(settings.SettingsError) as failure:
            settings.inspect_settings(config)
        self.assertNotIn(KEY, str(failure.exception))
        local = settings.default_settings()
        local["provider"]["model_name"] = KEY
        with self.assertRaises(settings.SettingsError):
            settings.validate_settings(local)

    def test_failed_apply_keeps_previous_and_restore_blocks_runs_without_fallback(self):
        supervisor = bridge.Supervisor()
        output = io.StringIO()
        supervisor.writer = bridge.JsonlWriter(output)
        def apply(config, restore=False):
            supervisor._settings({"type": "settings.apply", "request_id": "req_settings",
                                  "payload": {"config": config, "restore": restore}})
        apply(settings.default_settings())
        with patch.dict(os.environ, {KEY_ENV: ""}):
            apply(external())
            self.assertEqual(supervisor.settings_snapshot["config"], settings.default_settings())
            apply(external(), True)
        with patch.object(supervisor, "_spawn_worker") as spawn:
            supervisor._start({"type": "run.start", "request_id": "req_blocked", "payload": {"message": "hello"}})
            spawn.assert_not_called()
        frames = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(frames[-1]["error"]["code"], "settings_missing_credentials")
        self.assertTrue(all(frame["type"] == "response" for frame in frames))

    def test_busy_apply_does_not_change_active_mode(self):
        supervisor = bridge.Supervisor()
        supervisor.writer = bridge.JsonlWriter(io.StringIO())
        state = unittest.mock.Mock(terminal=False, cancelled=False)
        supervisor.runs["run_busy"] = state
        with patch.object(bridge, "inspect_settings", side_effect=AssertionError("changed active configuration")):
            supervisor._settings({"type": "settings.apply", "request_id": "req_busy",
                                  "payload": {"config": settings.default_settings(), "restore": False}})
        self.assertIsNone(supervisor.settings_snapshot)


if __name__ == "__main__":
    unittest.main()
