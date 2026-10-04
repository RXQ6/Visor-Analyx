"""Phase 2.7 controllable joint acceptance, never an external OpenAI test.

CLI modes are scripted and loopback HTTP only. The real Filesystem MCP, existing
factory/Provider adapter, AgentLoop, Registry and evaluators remain authoritative.
Only safe assertion summaries are printed or saved.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from agent.state import AgentState
from demo.provider_mcp_runtime import ProviderMCPRuntime
from eval_harness import EvalCase, EvalResult, EvalRunner
from mcp_adapter.readonly_filesystem import FILESYSTEM_ALLOWED_ROOT, FILESYSTEM_TOOL_NAME
from providers import OpenAICompatibleProvider
from tests.fixtures.provider_mcp_controlled import ControlledCompletionService, ScriptedMCPProvider


def observation_for_eval(state: AgentState) -> dict[str, Any]:
    """Use actual Agent state and actual ToolResult; never manufacture a call."""

    last_tool = next((item for item in reversed(state.messages) if item["role"] == "tool"), None)
    calls = [{"tool": item["tool_name"], "args": item["arguments"],
              "status": "ok" if item["success"] else "error"} for item in state.execution_trace]
    return {
        "passed": state.stop_reason == "final_answer" and bool(state.final_answer),
        "answer": state.final_answer,
        "contract_value": json.loads(last_tool["content"]) if last_tool is not None else None,
        "trace": {"available": bool(state.trace_events), "tool_calls": calls,
                  "loop_iterations": state.iteration, "max_iter": state.max_iter,
                  "stop_reason": state.stop_reason, "allowed_retries": 0},
        "trace_summary": {"available": bool(state.trace_events),
                          "tool_calls": [{"tool": item["tool"], "status": item["status"]} for item in calls]},
        "trace_events": state.trace_events,
    }


def joint_eval_case(executor: Callable[[], dict[str, Any]], case_id: str) -> EvalCase:
    return EvalCase(
        case_id, "provider_mcp_joint", "Provider tool selection and second turn using real MCP evidence",
        executor, suite="phase27-provider-mcp",
        expectations={
            "tools": {"expected": [FILESYSTEM_TOOL_NAME], "allowed": [FILESYSTEM_TOOL_NAME]},
            "contract": {"kind": "tool_result", "required": ["error", "duration", "truncated"],
                         "types": {"ok": "boolean", "duration": "number", "truncated": "boolean"}},
            "guardrail": {"tool": FILESYSTEM_TOOL_NAME, "decision": "allow"},
            "observability": {"required_events": ["mcp_called", "guardrail_decision", "tool_completed"]},
        },
        evaluators=("tool", "contract", "trace", "guardrail", "observability"),
    )


def evaluate_state(state: AgentState, case_id: str = "P27-JOINT-TEST") -> EvalResult:
    return EvalRunner().run_case(joint_eval_case(lambda: observation_for_eval(state), case_id))


def _run_in_harness(runtime: ProviderMCPRuntime, script: ScriptedMCPProvider, case_id: str) -> dict[str, Any]:
    captured: dict[str, AgentState] = {}

    def executor() -> dict[str, Any]:
        state = runtime.run("Query the public metadata fixture and explain its size.")
        captured["state"] = state
        return observation_for_eval(state)

    result = EvalRunner().run_case(joint_eval_case(executor, case_id))
    if not result.passed:
        raise AssertionError("Provider/MCP controllable Harness case failed")
    state = captured["state"]
    actual_size = (FILESYSTEM_ALLOWED_ROOT / "metadata.txt").stat().st_size
    expected_schema = next(item["function"] for item in runtime.registry.tool_schemas()
                           if item["function"]["name"] == FILESYSTEM_TOOL_NAME)
    assert script.calls == 2 and len(script.observations) == 1
    assert script.schemas == [expected_schema, expected_schema]
    assert script.observations[0] == json.loads(next(item for item in state.messages
                                                   if item["role"] == "tool")["content"])
    assert f"{actual_size} bytes" in state.final_answer
    assert result.tool_correct is True and result.contract_valid is True and result.trace_available
    assert result.tool_calls == 1 and result.loop_iterations == 2 and result.retry_count == 0
    return {
        "status": "PASS", "provider_turns": script.calls, "mcp_tool_calls": result.tool_calls,
        "schema_passed_unchanged": True, "observation_returned_to_provider": True,
        "metadata_matches_local_stat": True, "metadata_size_bytes": actual_size,
        "final_answer": "PASS", "stop_reason": state.stop_reason,
        "eval_harness": result.to_dict(),
    }


def run_scripted_acceptance(node_executable: str | Path) -> dict[str, Any]:
    script = ScriptedMCPProvider()
    with ProviderMCPRuntime(node_executable=node_executable, provider_factory=lambda _config: script) as runtime:
        result = _run_in_harness(runtime, script, "P27-SCRIPTED-MCP-01")
    result.update(provider_lane="scripted_factory", http_requests=0, external_model_requests=0)
    return result


def run_loopback_acceptance(node_executable: str | Path) -> dict[str, Any]:
    service = ControlledCompletionService()
    with service.running() as config:
        with ProviderMCPRuntime(node_executable=node_executable, provider_config=config) as runtime:
            assert isinstance(runtime.provider, OpenAICompatibleProvider)
            result = _run_in_harness(runtime, service.script, "P27-COMPATIBLE-LOOPBACK-MCP-01")
            assert service.requests == 2 and service.failures == []
            assert service.tool_schema_snapshots == service.script.schemas
            metadata = runtime.provider.observations.snapshot()
            assert len(metadata) == 2 and all(item.latency_ms >= 0 for item in metadata)
            result.update(internal_provider_observations=len(metadata))
    result.update(provider_lane="existing_openai_compatible_factory_loopback_only",
                  http_requests=service.requests, external_model_requests=0,
                  credentials="synthetic_test_environment_only")
    return result


def run_acceptance(node_executable: str | Path) -> dict[str, Any]:
    # Keep scripted validation first. Only synthetic loopback traffic follows.
    scripted = run_scripted_acceptance(node_executable)
    loopback = run_loopback_acceptance(node_executable)
    return {
        "phase": "2.7", "acceptance": "controllable_provider_plus_real_filesystem_mcp",
        "scripted": scripted, "openai_compatible_loopback": loopback,
        "external_openai_requests": 0, "real_api_key_read": False,
        "phase23_real_openai_acceptance": "INCOMPLETE_PREVIOUS_HTTP_429",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = run_acceptance(args.node)
    serialized = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output is not None:
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
