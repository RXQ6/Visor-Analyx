"""Explicit real-server acceptance; no real model, UI, credentials or network.

All tools/call traffic is initiated by AgentLoop through ToolRegistry. This
script reports safe assertions, not raw MCP requests, responses or Trace IDs.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent import AgentLoop
from eval_harness import EvalCase, EvalRunner
from mcp_adapter import MCPHost
from mcp_adapter.readonly_filesystem import (
    FILESYSTEM_ALLOWED_ROOT,
    FILESYSTEM_SERVER_VERSION,
    FILESYSTEM_TOOL_NAME,
    attach_readonly_filesystem,
)
from tools import build_default_registry


class MetadataAcceptanceModel:
    """Script only the choice of tool; metadata must come from the real server."""

    def __init__(self) -> None:
        self.observation: dict[str, Any] | None = None
        self.schema: dict[str, Any] | None = None

    def complete(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        if self.schema is None:
            self.schema = next(item["function"]["parameters"] for item in tools
                               if item["function"]["name"] == FILESYSTEM_TOOL_NAME)
            return {
                "type": "tool_call", "id": "filesystem-metadata-1",
                "name": FILESYSTEM_TOOL_NAME, "arguments": {"path": "metadata.txt"},
            }
        self.observation = json.loads(messages[-1]["content"])
        if not self.observation["ok"]:
            raise AssertionError("Real MCP metadata query failed")
        return {"type": "final_answer", "content": "文件元数据查询完成。"}


def _execute_acceptance(node_executable: str | Path) -> dict[str, Any]:
    registry = build_default_registry()
    original_names = {item["function"]["name"] for item in registry.tool_schemas()}
    host = MCPHost(registry)
    try:
        report = attach_readonly_filesystem(host, node_executable=node_executable)
        if not report.ok:
            raise AssertionError(f"MCP startup/discovery failed: {report.error['code']}")
        assert report.registered_tools == (FILESYSTEM_TOOL_NAME,)
        model = MetadataAcceptanceModel()
        state = AgentLoop(model, registry).run("查询公开测试文件的元数据。")
        assert state.stop_reason == "final_answer"
        assert model.schema["properties"]["path"]["type"] == "string"
        assert model.schema["required"] == ["path"]
        observation = model.observation
        assert observation is not None and observation["ok"]
        data = observation["data"]
        metadata = data["structuredContent"]["content"]
        actual_size = (FILESYSTEM_ALLOWED_ROOT / "metadata.txt").stat().st_size
        assert f"size: {actual_size}" in metadata
        assert "isFile: true" in metadata
        assert data["content"][0]["text"] == metadata
        assert data["server"] == "filesystem" and data["tool"] == "get_file_info"
        assert len(state.execution_trace) == 1 and state.execution_trace[0]["success"]
        event_types = {event["event_type"] for event in state.trace_events}
        assert {"tool_called", "guardrail_decision", "mcp_called", "tool_completed"} <= event_types
        final_names = {item["function"]["name"] for item in registry.tool_schemas()}
        assert final_names - original_names == {FILESYSTEM_TOOL_NAME}
        return {
            "server": "@modelcontextprotocol/server-filesystem",
            "package_version": FILESYSTEM_SERVER_VERSION,
            "transport": "official_mcp_sdk_stdio",
            "allowed_root": "tests/fixtures/mcp-readonly",
            "startup": "PASS", "list_tools": "PASS", "schema_mapping": "PASS",
            "registered_tools": list(report.registered_tools),
            "call_tool": "PASS", "tool_result": "PASS", "agent_loop": "PASS",
            "guardrail_and_mcp_trace": "PASS", "metadata_size_bytes": actual_size,
            "metadata_matches_local_stat": True, "file_content_read": False,
            "external_model_requests": 0,
            "_eval_observation": {
                "passed": True, "answer": state.final_answer,
                "contract_value": observation,
                "trace_summary": {
                    "available": True,
                    "tool_calls": [{"tool": item["tool_name"], "status": "ok" if item["success"] else "error"}
                                   for item in state.execution_trace],
                },
                "trace": {
                    "available": True,
                    "tool_calls": [{"tool": item["tool_name"], "status": "ok" if item["success"] else "error"}
                                   for item in state.execution_trace],
                    "loop_iterations": state.iteration, "max_iter": state.max_iter,
                    "stop_reason": state.stop_reason, "allowed_retries": 0,
                },
                "trace_events": state.trace_events,
            },
        }
    finally:
        host.close()


def run_acceptance(node_executable: str | Path) -> dict[str, Any]:
    """Run a separate optional case in the unchanged Day19 EvalRunner.

    It does not alter the legacy suites, baseline, thresholds or Regression Gate.
    Evaluators receive the actual ToolResult/Trace internally; the saved report
    contains only their safe summaries and the verified public file size.
    """

    acceptance: dict[str, Any] = {}

    def executor() -> dict[str, Any]:
        acceptance.update(_execute_acceptance(node_executable))
        return acceptance.pop("_eval_observation")

    case = EvalCase(
        "MCP-FILESYSTEM-01", "real_mcp", "Scoped external filesystem metadata via Registry and AgentLoop",
        executor, suite="phase26-real-mcp",
        expectations={
            "tools": {"expected": [FILESYSTEM_TOOL_NAME], "allowed": [FILESYSTEM_TOOL_NAME]},
            "contract": {"kind": "tool_result", "required": ["error", "duration", "truncated"],
                         "types": {"ok": "boolean", "data": "object", "duration": "number", "truncated": "boolean"}},
            "guardrail": {"tool": FILESYSTEM_TOOL_NAME, "decision": "allow"},
            "observability": {"required_events": ["mcp_called", "guardrail_decision", "tool_completed"]},
        },
        evaluators=("tool", "contract", "trace", "guardrail", "observability"),
    )
    result = EvalRunner().run_case(case)
    if not result.passed:
        raise AssertionError(f"Real MCP Harness case failed: {result.failure_reason}")
    assert result.tool_correct is True and result.contract_valid is True and result.trace_available
    acceptance["eval_harness"] = result.to_dict()
    return acceptance
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--node", required=True, help="Absolute host-owned Node executable")
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
