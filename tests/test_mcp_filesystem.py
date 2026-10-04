from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from agent import AgentLoop
from guardrails import GuardrailDecision
from mcp_adapter import MCPHost, MCPRemoteError, MCPStdioClient
from mcp_adapter.readonly_filesystem import (
    FILESYSTEM_ALLOWED_ROOT, FILESYSTEM_PACKAGE_ROOT, FILESYSTEM_TOOL_NAME,
    attach_readonly_filesystem,
)
from observability import TraceCollector
from tests.mcp_filesystem_smoke import MetadataAcceptanceModel, run_acceptance
from tools import build_default_registry


NODE = shutil.which("node")
RELAY = Path(__file__).resolve().parent / "fixtures" / "mcp_filesystem_fault_relay.cjs"


def names(registry):
    return {item["function"]["name"] for item in registry.tool_schemas()}


def wait_for_marker(marker: Path, text: str) -> bool:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if marker.exists() and text in marker.read_text("utf-8"):
            return True
        time.sleep(0.02)
    return False


class FilesystemMCPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if NODE is None:
            raise RuntimeError("Real MCP tests require a host Node executable")
        cls.registry = build_default_registry()
        cls.original_names = names(cls.registry)
        cls.host = MCPHost(cls.registry)
        cls.report = attach_readonly_filesystem(cls.host, node_executable=NODE)
        if not cls.report.ok:
            raise AssertionError(f"Real Filesystem MCP dependency/startup failed: {cls.report.error}")
        cls.client = cls.host._bindings["filesystem"].client

    @classmethod
    def tearDownClass(cls):
        cls.host.close()
        if cls.client._thread.is_alive():
            raise AssertionError("The owned MCP stdio thread did not close")

    def test_server_startup_and_real_list_tools(self):
        response = self.client.list_tools(timeout_seconds=5)
        discovered = {item["name"] for item in response["tools"]}
        self.assertIn("get_file_info", discovered)
        self.assertIn("write_file", discovered)  # advertised upstream, never granted
        self.assertEqual(self.report.registered_tools, (FILESYSTEM_TOOL_NAME,))
        self.assertEqual(names(self.registry) - self.original_names, {FILESYSTEM_TOOL_NAME})
        self.assertEqual(self.host.server_ids, ("filesystem",))

    def test_input_schema_is_mapped_without_fabrication(self):
        remote = next(item for item in self.client.list_tools(timeout_seconds=5)["tools"]
                      if item["name"] == "get_file_info")
        local = self.registry.get(FILESYSTEM_TOOL_NAME)
        self.assertEqual(local.parameter_schema, remote["inputSchema"])
        self.assertEqual(local.parameter_schema["required"], ["path"])
        self.assertEqual(local.parameter_schema["properties"]["path"]["type"], "string")
        self.assertEqual(local.guardrail_policy.action_type, "mcp_read")
        self.assertEqual(local.guardrail_policy.tool_kind, "mcp")

    def test_real_call_tool_and_existing_tool_result(self):
        result = self.registry.execute(FILESYSTEM_TOOL_NAME, {"path": "metadata.txt"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(set(result), {"ok", "data", "error", "duration", "truncated"})
        metadata = result["data"]["structuredContent"]["content"]
        self.assertIn(f"size: {(FILESYSTEM_ALLOWED_ROOT / 'metadata.txt').stat().st_size}", metadata)
        self.assertIn("isFile: true", metadata)
        self.assertEqual(metadata, result["data"]["content"][0]["text"])
        self.assertNotIn("Public Phase", metadata)  # content was not read
        self.assertFalse(result["truncated"])

    def test_directory_metadata_is_read_only(self):
        result = self.registry.execute(FILESYSTEM_TOOL_NAME, {"path": "."})
        self.assertTrue(result["ok"], result)
        self.assertIn("isDirectory: true", result["data"]["structuredContent"]["content"])

    def test_real_agent_loop_and_safe_trace(self):
        model = MetadataAcceptanceModel()
        state = AgentLoop(model, self.registry).run("查询公开文件元数据")
        self.assertEqual(state.stop_reason, "final_answer")
        self.assertTrue(state.execution_trace[0]["success"])
        self.assertEqual(state.execution_trace[0]["tool_name"], FILESYSTEM_TOOL_NAME)
        events = state.trace_events
        self.assertTrue(any(event["event_type"] == "mcp_called" for event in events))
        self.assertTrue(any(event["event_type"] == "guardrail_decision"
                            and event["status"] == "allow" for event in events))
        serialized = json.dumps(events)
        self.assertNotIn("metadata.txt", serialized)
        self.assertNotIn("structuredContent", serialized)
        self.assertNotIn(str(FILESYSTEM_ALLOWED_ROOT), serialized)

    def test_parent_absolute_and_prefix_sibling_paths_are_denied(self):
        for path in ("../sales.csv", str(FILESYSTEM_ALLOWED_ROOT.parent / "sales.csv"),
                     str(FILESYSTEM_ALLOWED_ROOT.parent / "mcp-readonly-escape" / "data.csv")):
            with self.subTest(path=path):
                result = self.registry.execute(FILESYSTEM_TOOL_NAME, {"path": path})
                self.assertFalse(result["ok"])
                self.assertEqual(result["error"]["code"], "mcp_tool_error")
                self.assertIsNone(result["data"])
                self.assertIn("Access denied", result["error"]["message"])

    def test_no_content_write_edit_move_or_shell_tools_are_granted(self):
        fixture = FILESYSTEM_ALLOWED_ROOT / "metadata.txt"
        original = hashlib.sha256(fixture.read_bytes()).digest()
        for tool in ("write_file", "edit_file", "move_file", "create_directory",
                     "read_text_file", "read_file", "execute_shell"):
            result = self.registry.execute(f"mcp_filesystem__{tool}", {"path": "metadata.txt"})
            self.assertFalse(result["ok"])
            self.assertEqual(result["error"]["code"], "TOOL_NOT_FOUND")
        self.assertEqual(hashlib.sha256(fixture.read_bytes()).digest(), original)

    def test_invalid_arguments_never_reach_real_transport(self):
        with patch.object(self.client, "call_tool", wraps=self.client.call_tool) as call:
            for arguments in ({}, {"path": 123}):
                self.assertEqual(self.registry.execute(FILESYSTEM_TOOL_NAME, arguments)["error"]["code"],
                                 "invalid_arguments")
            call.assert_not_called()

    def test_guardrail_block_prevents_real_call(self):
        block = GuardrailDecision("block", "acceptance_block", "Blocked in acceptance",
                                  FILESYSTEM_TOOL_NAME, "mcp_read", "low", "mcp")
        collector = TraceCollector()
        with patch.object(self.registry.guardrail, "evaluate", return_value=block), \
             patch.object(self.client, "call_tool", wraps=self.client.call_tool) as call:
            result = self.registry.execute(FILESYSTEM_TOOL_NAME, {"path": "metadata.txt"},
                                           context={"_trace_collector": collector})
            self.assertEqual(result["error"]["code"], "guardrail_blocked")
            call.assert_not_called()
        self.assertFalse(any(event["event_type"] == "mcp_called" for event in collector.snapshot()))

    def test_real_result_uses_existing_truncation(self):
        definition = self.registry.get(FILESYSTEM_TOOL_NAME)
        # Change only this test binding's result limit, never the Registry algorithm.
        self.registry._tools[FILESYSTEM_TOOL_NAME] = replace(definition, max_result_bytes=256)
        try:
            result = self.registry.execute(FILESYSTEM_TOOL_NAME, {"path": "metadata.txt"})
            self.assertTrue(result["ok"])
            self.assertTrue(result["truncated"])
            self.assertLessEqual(len(json.dumps(result["data"], ensure_ascii=False,
                                               separators=(",", ":")).encode()), 256)
        finally:
            self.registry._tools[FILESYSTEM_TOOL_NAME] = definition

    def test_default_registry_is_not_implicitly_changed(self):
        self.assertEqual(names(build_default_registry()), self.original_names)


class FilesystemMCPCompositionTests(unittest.TestCase):
    def test_unavailable_node_fails_without_changing_registry(self):
        registry = build_default_registry()
        before = names(registry)
        host = MCPHost(registry)
        with tempfile.TemporaryDirectory() as directory:
            report = attach_readonly_filesystem(host, node_executable=Path(directory) / "node.exe")
        self.assertFalse(report.ok)
        self.assertEqual(report.error["code"], "mcp_server_unavailable")
        self.assertEqual(names(registry), before)
        self.assertEqual(host.server_ids, ())

    def test_missing_optional_package_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as directory, \
             patch("mcp_adapter.readonly_filesystem.FILESYSTEM_PACKAGE_ROOT", Path(directory)):
            host = MCPHost(build_default_registry())
            report = attach_readonly_filesystem(host, node_executable=NODE)
            self.assertFalse(report.ok)
            self.assertEqual(report.error["code"], "mcp_dependency_missing")
            self.assertEqual(host.server_ids, ())

    def test_no_credentials_provider_config_or_node_options_are_inherited(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "synthetic-mcp-not-a-real-key",
                                      "DATA_AGENT_PROVIDER_ENDPOINT": "synthetic-private-config",
                                      "NODE_OPTIONS": "--invalid-mcp-test-option"}):
            result = run_acceptance(NODE)
        self.assertEqual(result["call_tool"], "PASS")
        self.assertTrue(result["eval_harness"]["passed"])
        self.assertTrue(result["eval_harness"]["tool_correct"])
        self.assertTrue(result["eval_harness"]["contract_valid"])
        self.assertEqual(result["eval_harness"]["tool_calls"], 1)
        self.assertNotIn("synthetic", json.dumps(result))

    def test_sdk_startup_failure_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(MCPRemoteError):
                MCPStdioClient(NODE, args=[str(Path(directory) / "absent.cjs")], env={},
                               startup_timeout_seconds=3)

    def test_composition_passes_only_fixed_root_and_permission_set(self):
        with patch("mcp_adapter.readonly_filesystem.MCPStdioClient") as client_type:
            host = MCPHost(build_default_registry())
            # Let discovery fail safely after capturing launch parameters.
            client_type.return_value.list_tools.side_effect = MCPRemoteError("unavailable")
            report = attach_readonly_filesystem(host, node_executable=NODE)
            self.assertFalse(report.ok)
            kwargs = client_type.call_args.kwargs
            self.assertEqual(kwargs["env"], {})
            self.assertEqual(kwargs["cwd"], FILESYSTEM_ALLOWED_ROOT)
            self.assertEqual(kwargs["args"], [str(FILESYSTEM_PACKAGE_ROOT / "dist" / "index.js"),
                                             str(FILESYSTEM_ALLOWED_ROOT)])
            client_type.return_value.close.assert_called_once()


class FilesystemMCPWireFaultTests(unittest.TestCase):
    def connect(self, mode, marker=None, timeout=2):
        registry = build_default_registry()
        client = MCPStdioClient(NODE, args=[str(RELAY), str(FILESYSTEM_PACKAGE_ROOT / "dist" / "index.js"),
                                           str(FILESYSTEM_ALLOWED_ROOT), mode, str(marker) if marker else ""],
                                env={}, cwd=FILESYSTEM_ALLOWED_ROOT)
        host = MCPHost(registry)
        report = host.attach_server(client, server_id="filesystem", allowed_tools={"get_file_info"},
                                    call_timeout_seconds=timeout)
        self.addCleanup(client.close)
        self.addCleanup(host.close)
        return registry, client, report

    def test_invalid_schema_is_rejected_atomically(self):
        registry, _, report = self.connect("bad-schema")
        self.assertFalse(report.ok)
        self.assertEqual(report.error["code"], "mcp_schema_incompatible")
        self.assertNotIn(FILESYSTEM_TOOL_NAME, names(registry))

    def test_invalid_wire_response_is_protocol_error(self):
        registry, _, report = self.connect("malformed")
        self.assertTrue(report.ok, report.error)
        result = registry.execute(FILESYSTEM_TOOL_NAME, {"path": "metadata.txt"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["code"], "mcp_protocol_error")
        self.assertIsNone(result["data"])

    def test_invalid_structured_output_is_protocol_error(self):
        registry, _, report = self.connect("bad-output")
        self.assertTrue(report.ok, report.error)
        result = registry.execute(FILESYSTEM_TOOL_NAME, {"path": "metadata.txt"})
        self.assertEqual(result["error"]["code"], "mcp_protocol_error")

    def test_missing_structured_output_is_protocol_error(self):
        registry, _, report = self.connect("missing-output")
        self.assertTrue(report.ok, report.error)
        result = registry.execute(FILESYSTEM_TOOL_NAME, {"path": "metadata.txt"})
        self.assertEqual(result["error"]["code"], "mcp_protocol_error")

    def test_startup_timeout_cleans_owned_stdio_thread(self):
        before = {thread.ident for thread in threading.enumerate() if thread.name == "mcp-sdk-stdio-client"}
        with self.assertRaises(MCPRemoteError):
            MCPStdioClient(NODE, args=[str(RELAY), str(FILESYSTEM_PACKAGE_ROOT / "dist" / "index.js"),
                                      str(FILESYSTEM_ALLOWED_ROOT), "stall-startup", ""],
                           env={}, startup_timeout_seconds=0.5)
        after = {thread.ident for thread in threading.enumerate() if thread.name == "mcp-sdk-stdio-client"}
        self.assertEqual(after, before)

    def test_peer_disconnect_is_server_unavailable(self):
        registry, _, report = self.connect("disconnect")
        self.assertTrue(report.ok, report.error)
        result = registry.execute(FILESYSTEM_TOOL_NAME, {"path": "metadata.txt"})
        self.assertEqual(result["error"]["code"], "mcp_server_unavailable")

    def test_timeout_cancels_sdk_request_and_connection_can_be_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "wire-marker.txt"
            registry, _, report = self.connect("delay", marker, timeout=0.4)
            self.assertTrue(report.ok, report.error)
            started = time.perf_counter()
            result = registry.execute(FILESYSTEM_TOOL_NAME, {"path": "metadata.txt"})
            self.assertEqual(result["error"]["code"], "mcp_timeout")
            self.assertLess(time.perf_counter() - started, 1.5)
            self.assertTrue(wait_for_marker(marker, "real_call_completed"))
            self.assertTrue(wait_for_marker(marker, "cancel_notification"))
            follow_up = registry.execute(FILESYSTEM_TOOL_NAME, {"path": "metadata.txt"})
            self.assertTrue(follow_up["ok"], follow_up)

    def test_explicit_cancellation_reaches_wire_and_unblocks_registry(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "wire-marker.txt"
            registry, client, report = self.connect("delay", marker, timeout=4)
            self.assertTrue(report.ok, report.error)
            results = []
            worker = threading.Thread(target=lambda: results.append(
                registry.execute(FILESYSTEM_TOOL_NAME, {"path": "metadata.txt"})))
            worker.start()
            self.assertTrue(wait_for_marker(marker, "real_call_completed"))
            client.cancel_pending()
            worker.join(2)
            self.assertFalse(worker.is_alive())
            self.assertEqual(results[0]["error"]["code"], "mcp_timeout")
            self.assertTrue(wait_for_marker(marker, "cancel_notification"))


if __name__ == "__main__":
    unittest.main()
