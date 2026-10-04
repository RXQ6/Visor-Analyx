from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from demo.provider_mcp_runtime import ProviderMCPRuntime, ProviderMCPRuntimeError
from eval_harness.taxonomy import FailureType
from guardrails import GuardrailDecision
from mcp_adapter import MCPStdioClient
from mcp_adapter.readonly_filesystem import FILESYSTEM_ALLOWED_ROOT, FILESYSTEM_TOOL_NAME
from observability import TraceCollector
from providers import (
    DeterministicModelProvider, ModelProvider, OpenAICompatibleProvider,
    ProviderConfig, ProviderInvalidResponseError, UnknownProviderError, create_provider,
)
from tests.fixtures.provider_mcp_controlled import (
    ControlledCompletionService, ScriptedMCPProvider, SYNTHETIC_KEY, SYNTHETIC_KEY_ENV,
)
from tests.provider_mcp_smoke import evaluate_state, run_scripted_acceptance


NODE = shutil.which("node")
RELAY = Path(__file__).resolve().parent / "fixtures" / "mcp_filesystem_fault_relay.cjs"


def fault_transport(mode: str):
    """Inject only a wire fault around the exact Phase 2.6 external server."""
    def create(command, *, args, **kwargs):
        return MCPStdioClient(command, args=[str(RELAY), *args, mode, ""], **kwargs)
    return patch("mcp_adapter.readonly_filesystem.MCPStdioClient", side_effect=create)


class ScriptedProviderMCPJointTests(unittest.TestCase):
    def runtime(self, mode="happy", **kwargs):
        script = ScriptedMCPProvider(mode)
        runtime = ProviderMCPRuntime(node_executable=NODE, provider_factory=lambda _config: script, **kwargs)
        self.addCleanup(runtime.close)
        return runtime, script

    def test_provider_selects_real_mcp_tool_from_unchanged_schema(self):
        runtime, script = self.runtime()
        state = runtime.run("Query the public metadata fixture")
        self.assertIs(runtime.agent.model, runtime.provider)
        self.assertIsInstance(script, ModelProvider)
        self.assertEqual(script.schemas[0]["parameters"], runtime.registry.get(FILESYSTEM_TOOL_NAME).parameter_schema)
        self.assertEqual(state.tool_calls[0]["name"], FILESYSTEM_TOOL_NAME)
        self.assertTrue(state.execution_trace[0]["success"])

    def test_mcp_observation_returns_to_same_provider_second_turn(self):
        runtime, script = self.runtime()
        state = runtime.run("Query the public metadata fixture")
        observation_message = next(message for message in state.messages if message["role"] == "tool")
        self.assertEqual(script.calls, 2)
        self.assertEqual(script.observations, [json.loads(observation_message["content"])])
        self.assertEqual(script.tool_call_ids, [state.tool_calls[0]["id"]])
        self.assertEqual(script.schemas[0], script.schemas[1])
        self.assertEqual(script.observations[0]["data"], state.execution_trace[0]["data"])

    def test_final_answer_uses_actual_mcp_evidence_and_ends_normally(self):
        runtime, _ = self.runtime()
        state = runtime.run("Query the public metadata fixture")
        self.assertEqual(state.stop_reason, "final_answer")
        self.assertEqual(state.iteration, 2)
        size = (FILESYSTEM_ALLOWED_ROOT / "metadata.txt").stat().st_size
        self.assertEqual(state.final_answer, f"metadata.txt size: {size} bytes.")
        result = evaluate_state(state)
        self.assertTrue(result.passed, result.failure_reason)
        self.assertTrue(result.tool_correct)
        self.assertTrue(result.contract_valid)
        self.assertEqual(result.tool_calls, 1)

    def test_scripted_factory_is_explicit_and_original_eval_runner_executes_closed_loop(self):
        result = run_scripted_acceptance(NODE)
        self.assertEqual(result["provider_lane"], "scripted_factory")
        self.assertEqual(result["provider_turns"], 2)
        self.assertEqual(result["http_requests"], 0)
        self.assertEqual(result["eval_harness"]["loop_iterations"], 2)
        self.assertTrue(all(item["passed"] for item in result["eval_harness"]["process_evaluations"]))

    def test_invalid_tool_is_not_executed_and_eval_detects_it(self):
        runtime, script = self.runtime("invalid_tool")
        client = runtime.host._bindings["filesystem"].client
        with patch.object(client, "call_tool", wraps=client.call_tool) as call:
            state = runtime.run("Try an unavailable MCP tool")
        call.assert_not_called()
        self.assertEqual(script.observations[0]["error"]["code"], "TOOL_NOT_FOUND")
        self.assertEqual(state.stop_reason, "final_answer")
        self.assertFalse(any(event["event_type"] == "mcp_called" for event in state.trace_events))
        result = evaluate_state(state)
        self.assertFalse(result.passed)
        self.assertEqual(result.failure_type, str(FailureType.SECURITY_VIOLATION))

    def test_repeated_read_calls_are_visible_and_fail_original_eval(self):
        runtime, script = self.runtime("repeat")
        state = runtime.run("Repeat the same query")
        self.assertEqual(script.calls, 3)
        self.assertEqual(len(state.execution_trace), 2)
        self.assertTrue(all(item["success"] for item in state.execution_trace))
        self.assertEqual(state.stop_reason, "final_answer")
        result = evaluate_state(state)
        self.assertFalse(result.passed)
        self.assertEqual(result.retry_count, 1)
        self.assertEqual(result.failure_type, str(FailureType.TOOL_SELECTION_ERROR))
        self.assertFalse(next(item for item in result.process_evaluations if item["evaluator"] == "trace")["passed"])

    def test_always_repeating_provider_remains_bounded_by_existing_max_iter(self):
        runtime, script = self.runtime("always_repeat", max_iter=3)
        state = runtime.run("Repeat without a final answer")
        self.assertEqual(script.calls, 3)
        self.assertEqual(len(state.execution_trace), 3)
        self.assertEqual(state.stop_reason, "max_iter")
        self.assertIsNone(state.final_answer)
        self.assertFalse(evaluate_state(state).passed)

    def test_guardrail_block_ends_before_remote_io_or_second_provider_turn(self):
        runtime, script = self.runtime()
        client = runtime.host._bindings["filesystem"].client
        blocked = GuardrailDecision("block", "phase27_block", "Acceptance block", FILESYSTEM_TOOL_NAME,
                                    "mcp_read", "low", "mcp")
        with patch.object(runtime.registry.guardrail, "evaluate", return_value=blocked), \
             patch.object(client, "call_tool", wraps=client.call_tool) as call:
            state = runtime.run("Query with a blocked guardrail")
        call.assert_not_called()
        self.assertEqual(script.calls, 1)
        self.assertEqual(state.stop_reason, "guardrail_blocked")
        self.assertIsNone(state.final_answer)
        self.assertFalse(evaluate_state(state).passed)

    def test_trace_and_eval_agree_on_calls_order_and_contract(self):
        runtime, _ = self.runtime()
        state = runtime.run("Query the public metadata fixture")
        result = evaluate_state(state)
        types = [event["event_type"] for event in state.trace_events]
        self.assertLess(types.index("guardrail_decision"), types.index("mcp_called"))
        self.assertLess(types.index("mcp_called"), types.index("tool_completed"))
        self.assertEqual(result.tool_calls, len(state.execution_trace))
        self.assertEqual(result.tool_calls, types.count("mcp_called"))
        self.assertEqual(result.loop_iterations, state.iteration)
        self.assertEqual(result.retry_count, 0)
        self.assertNotIn("metadata.txt", json.dumps(state.trace_events))
        self.assertNotIn("structuredContent", json.dumps(state.trace_events))


class ProviderMCPCompositionTests(unittest.TestCase):
    def test_default_factory_and_original_deterministic_behavior_are_preserved(self):
        with patch("demo.provider_mcp_runtime.create_provider", wraps=create_provider) as factory:
            with ProviderMCPRuntime(node_executable=NODE) as runtime:
                self.assertIsInstance(runtime.provider, DeterministicModelProvider)
                state = runtime.run("hello")
        factory.assert_called_once_with(None)
        self.assertEqual(state.final_answer, "Desktop Runtime 已完成本次请求。")
        self.assertEqual(state.tool_calls, [])

    def test_unknown_provider_fails_before_mcp_start_without_fallback(self):
        with patch("demo.provider_mcp_runtime.attach_readonly_filesystem") as attach:
            with self.assertRaises(UnknownProviderError):
                ProviderMCPRuntime(node_executable=NODE, provider_config=ProviderConfig(provider_id="unknown"))
            attach.assert_not_called()

    def test_missing_mcp_fails_composition_without_running_provider(self):
        script = ScriptedMCPProvider()
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ProviderMCPRuntimeError) as raised:
                ProviderMCPRuntime(node_executable=Path(directory) / "node.exe",
                                   provider_factory=lambda _config: script)
        self.assertEqual(raised.exception.code, "mcp_server_unavailable")
        self.assertEqual(script.calls, 0)

    def test_runtime_close_cleans_connection_and_prevents_reuse(self):
        runtime = ProviderMCPRuntime(node_executable=NODE)
        client = runtime.host._bindings["filesystem"].client
        runtime.close()
        runtime.close()
        self.assertFalse(client._thread.is_alive())
        self.assertEqual(runtime.host.server_ids, ())
        with self.assertRaises(RuntimeError):
            runtime.run("hello")


class CompatibleProviderRealMCPJointTests(unittest.TestCase):
    def test_existing_factory_adapter_http_two_turns_and_real_mcp(self):
        service = ControlledCompletionService()
        with service.running() as config:
            with patch("demo.provider_mcp_runtime.create_provider", wraps=create_provider) as factory:
                with ProviderMCPRuntime(node_executable=NODE, provider_config=config) as runtime:
                    self.assertIsInstance(runtime.provider, OpenAICompatibleProvider)
                    state = runtime.run("Query the public metadata fixture")
                    metadata = runtime.provider.observations.snapshot()
                    schema = next(item["function"] for item in runtime.registry.tool_schemas()
                                  if item["function"]["name"] == FILESYSTEM_TOOL_NAME)
                    self.assertEqual(service.tool_schema_snapshots, [schema, schema])
            factory.assert_called_once_with(config)
        self.assertEqual(service.requests, 2)
        self.assertEqual(service.failures, [])
        self.assertEqual(service.script.observations, [json.loads(next(item for item in state.messages
                                                                      if item["role"] == "tool")["content"])])
        self.assertEqual(len(metadata), 2)
        self.assertTrue(all(item.latency_ms >= 0 for item in metadata))
        self.assertEqual(state.stop_reason, "final_answer")
        self.assertTrue(evaluate_state(state).passed)

    def test_loopback_credentials_config_and_usage_do_not_enter_agent_or_trace(self):
        service = ControlledCompletionService()
        with service.running() as config:
            with ProviderMCPRuntime(node_executable=NODE, provider_config=config) as runtime:
                state = runtime.run("Query the public metadata fixture")
                metadata = runtime.provider.observations.snapshot()
        serialized = json.dumps([state.messages, state.trace_events, state.execution_trace])
        for marker in (SYNTHETIC_KEY, SYNTHETIC_KEY_ENV, config.endpoint, config.model_name,
                       "Authorization", "prompt_tokens", "completion_tokens", '"provider_config"'):
            self.assertNotIn(marker, serialized)
        self.assertEqual([item.input_tokens for item in metadata], [40, 40])
        self.assertEqual([item.output_tokens for item in metadata], [12, 12])

    def test_compatible_adapter_rejects_unknown_tool_before_registry_call(self):
        service = ControlledCompletionService("invalid_tool")
        with service.running() as config:
            with ProviderMCPRuntime(node_executable=NODE, provider_config=config) as runtime:
                collector = TraceCollector()
                client = runtime.host._bindings["filesystem"].client
                with patch.object(client, "call_tool", wraps=client.call_tool) as call:
                    with self.assertRaises(ProviderInvalidResponseError):
                        runtime.run("Try an unavailable tool", trace_collector=collector)
                call.assert_not_called()
        self.assertEqual(service.requests, 1)
        self.assertFalse(any(event["event_type"] == "mcp_called" for event in collector.snapshot()))
        self.assertTrue(any(event["event_type"] == "error" for event in collector.snapshot()))

    def test_compatible_provider_gets_timeout_observation_and_does_not_retry(self):
        self.assert_fault_observation("delay", "mcp_timeout", timeout=0.4)

    def test_compatible_provider_gets_disconnect_observation_and_does_not_retry(self):
        self.assert_fault_observation("disconnect", "mcp_server_unavailable")

    def assert_fault_observation(self, mode, code, timeout=3):
        service = ControlledCompletionService()
        with service.running() as config, fault_transport(mode):
            with ProviderMCPRuntime(node_executable=NODE, provider_config=config,
                                    mcp_call_timeout_seconds=timeout) as runtime:
                state = runtime.run("Query with a wire fault")
        self.assertEqual(service.requests, 2)
        self.assertEqual(service.failures, [])
        self.assertEqual(service.script.calls, 2)
        self.assertFalse(service.script.observations[0]["ok"])
        self.assertEqual(service.script.observations[0]["error"]["code"], code)
        self.assertEqual(state.final_answer, "Tool failed: " + code)
        self.assertEqual(state.stop_reason, "final_answer")
        self.assertEqual(len(state.execution_trace), 1)
        result = evaluate_state(state)
        self.assertFalse(result.passed)  # Recovery text is not a successful tool result.
        self.assertTrue(result.contract_valid)
        self.assertEqual(result.failure_type, str(FailureType.TOOL_EXECUTION_ERROR))


if __name__ == "__main__":
    unittest.main()
