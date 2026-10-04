"""Test-only providers and loopback Chat Completions service.

The script chooses a tool; facts must come back from the real MCP ToolResult.
Only selected schema and tool observations are inspected in memory. No full
prompt, HTTP headers, body or response is logged or written to a report.
"""

from __future__ import annotations

import copy
import json
import os
import re
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Iterator

from mcp_adapter.readonly_filesystem import FILESYSTEM_TOOL_NAME
from providers import ProviderConfig


SYNTHETIC_KEY_ENV = "PHASE27_CONTROLLED_API_KEY"
SYNTHETIC_KEY = "synthetic-phase27-not-a-real-credential"


class ScriptedMCPProvider:
    def __init__(self, mode: str = "happy") -> None:
        self.mode = mode
        self.calls = 0
        self.schemas: list[dict[str, Any]] = []
        self.observations: list[dict[str, Any]] = []
        self.tool_call_ids: list[str] = []

    def complete(self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls += 1
        function = next(item["function"] for item in tools if item["function"]["name"] == FILESYSTEM_TOOL_NAME)
        if function["parameters"]["properties"]["path"]["type"] != "string":
            raise AssertionError("MCP path schema was not passed to Provider")
        self.schemas.append(copy.deepcopy(function))
        last_tool = next((message for message in reversed(messages) if message["role"] == "tool"), None)
        if last_tool is not None:
            self.observations.append(json.loads(last_tool["content"]))
            self.tool_call_ids.append(last_tool["tool_call_id"])
        if self.calls == 1 or self.mode == "always_repeat" or (self.mode == "repeat" and self.calls == 2):
            name = "mcp_filesystem__write_file" if self.mode == "invalid_tool" else function["name"]
            return {"type": "tool_call", "id": f"phase27-call-{self.calls}",
                    "name": name, "arguments": {"path": "metadata.txt"}}
        if last_tool is None:
            raise AssertionError("Provider second turn did not receive a tool observation")
        observation = self.observations[-1]
        if not observation["ok"]:
            return {"type": "final_answer", "content": "Tool failed: " + observation["error"]["code"]}
        data = observation["data"]
        if data["server"] != "filesystem" or data["tool"] != "get_file_info":
            raise AssertionError("Provider received the wrong MCP result")
        metadata = data["structuredContent"]["content"]
        if metadata != data["content"][0]["text"]:
            raise AssertionError("MCP text and structured result disagree")
        size = next((match.group(1) for line in metadata.splitlines()
                     if (match := re.fullmatch(r"size: (\d+)", line))), None)
        if size is None:
            raise AssertionError("MCP result omitted file size")
        return {"type": "final_answer", "content": f"metadata.txt size: {size} bytes."}


class ControlledCompletionService:
    """Loopback only; this is not an OpenAI or other external model service."""

    def __init__(self, mode: str = "happy") -> None:
        self.script = ScriptedMCPProvider(mode)
        self.requests = 0
        self.failures: list[str] = []
        self.tool_schema_snapshots: list[dict[str, Any]] = []
        service = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: object) -> None:
                pass

            def do_POST(self) -> None:
                service.requests += 1
                try:
                    if self.path != "/v1/chat/completions":
                        raise AssertionError("request_path")
                    if self.headers.get("Authorization") != "Bearer " + SYNTHETIC_KEY:
                        raise AssertionError("synthetic_auth")
                    length = int(self.headers["Content-Length"])
                    if length > 128 * 1024:
                        raise AssertionError("request_too_large")
                    payload = json.loads(self.rfile.read(length))
                    if payload["model"] != "phase27-controlled-model" or payload["stream"] is not False:
                        raise AssertionError("request_model")
                    if payload.get("parallel_tool_calls") is not False or payload.get("tool_choice") != "auto":
                        raise AssertionError("request_tool_options")
                    if SYNTHETIC_KEY in json.dumps(payload):
                        raise AssertionError("credential_in_body")
                    function = next(item["function"] for item in payload["tools"]
                                    if item["function"]["name"] == FILESYSTEM_TOOL_NAME)
                    service.tool_schema_snapshots.append(copy.deepcopy(function))
                    tool_messages = [item for item in payload["messages"] if item["role"] == "tool"]
                    if tool_messages:
                        assistant = next(item for item in reversed(payload["messages"])
                                         if item["role"] == "assistant" and item.get("tool_calls"))
                        if tool_messages[-1]["tool_call_id"] != assistant["tool_calls"][0]["id"]:
                            raise AssertionError("tool_call_id_mismatch")
                    decision = service.script.complete(messages=payload["messages"], tools=payload["tools"])
                    if decision["type"] == "tool_call":
                        choice = {"finish_reason": "tool_calls", "message": {
                            "role": "assistant", "content": None, "tool_calls": [{
                                "id": decision["id"], "type": "function", "function": {
                                    "name": decision["name"], "arguments": json.dumps(decision["arguments"]),
                                },
                            }],
                        }}
                    else:
                        choice = {"finish_reason": "stop", "message": {
                            "role": "assistant", "content": decision["content"],
                        }}
                    body = {"choices": [choice], "usage": {"prompt_tokens": 40, "completion_tokens": 12}}
                    encoded = json.dumps(body).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(encoded)))
                    self.send_header("x-request-id", f"req_phase27_{service.requests}")
                    self.end_headers()
                    self.wfile.write(encoded)
                except Exception as error:
                    # Fixed class only: never log payload/headers/exception text.
                    service.failures.append(type(error).__name__)
                    self.send_response(500)
                    self.send_header("Content-Length", "0")
                    self.end_headers()

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @contextmanager
    def running(self) -> Iterator[ProviderConfig]:
        self.thread.start()
        previous_test_key = os.environ.get(SYNTHETIC_KEY_ENV)
        try:
            # Touch only this test variable; do not snapshot the ambient environment.
            os.environ[SYNTHETIC_KEY_ENV] = SYNTHETIC_KEY
            yield ProviderConfig(
                provider_id="openai-compatible", model_name="phase27-controlled-model",
                endpoint=f"http://127.0.0.1:{self.server.server_port}/v1/chat/completions",
                api_key_env=SYNTHETIC_KEY_ENV, timeout_seconds=3.0,
            )
        finally:
            if previous_test_key is None:
                os.environ.pop(SYNTHETIC_KEY_ENV, None)
            else:
                os.environ[SYNTHETIC_KEY_ENV] = previous_test_key
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(2)
