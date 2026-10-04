from __future__ import annotations

import copy
import io
import json
import logging
import os
import threading
import tempfile
import traceback
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from providers import (
    DeterministicModelProvider, MissingAPIKeyError, ModelProvider,
    OpenAICompatibleProvider, ProviderAuthenticationError, ProviderConfig,
    ProviderConfigError, ProviderHTTPError, ProviderInvalidResponseError,
    ProviderNetworkError, ProviderRequestError, ProviderTimeoutError, create_provider,
)


ROOT = Path(__file__).resolve().parents[1]
# Synthetic test credential; never a usable API key.
KEY = "synthetic-provider-credential-23"
ENV_NAME = "PHASE23_SYNTHETIC_API_KEY"
TEXT_REQUEST = {"messages": [{"role": "user", "content": "hello"}], "tools": []}
TOOL = {
    "type": "function",
    "function": {
        "name": "basic_stats", "description": "Read deterministic statistics",
        "parameters": {"type": "object", "properties": {"column": {"type": "string"}}},
    },
}


def config(**kwargs) -> ProviderConfig:
    return ProviderConfig(**{
        "provider_id": "openai-compatible", "model_name": "synthetic-model",
        "endpoint": "https://provider.invalid/v1", "api_key_env": ENV_NAME, **kwargs,
    })


def final_response(content: str = "Hello") -> dict:
    return {"id": "raw-vendor-id", "usage": {"total_tokens": 17}, "choices": [{
        "finish_reason": "stop", "message": {"role": "assistant", "content": content},
    }]}


def tool_response(arguments: str = '{"column":"销售额"}') -> dict:
    return {"choices": [{"finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None, "tool_calls": [{
            "id": "call-provider-1", "type": "function",
            "function": {"name": "basic_stats", "arguments": arguments},
        }],
    }}]}


def response(body: dict | bytes, *, status: int = 200) -> MagicMock:
    mock = MagicMock()
    mock.__enter__.return_value = mock
    mock.status = status
    mock.read.return_value = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
    return mock


class OpenAICompatibleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.environment = patch.dict(os.environ, {ENV_NAME: KEY})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.opener_patch = patch("providers.openai_compatible.build_opener")
        self.opener = self.opener_patch.start().return_value
        self.addCleanup(self.opener_patch.stop)
        self.opener.open.return_value = response(final_response())

    def test_factory_explicit_real_provider_and_default_remains_offline(self) -> None:
        with patch("providers.openai_compatible.os.environ.get", side_effect=AssertionError("unexpected credential read")):
            self.assertIsInstance(create_provider(), DeterministicModelProvider)
            self.assertIsInstance(create_provider("deterministic"), DeterministicModelProvider)
        provider = create_provider(config())
        self.assertIsInstance(provider, OpenAICompatibleProvider)
        self.assertIsInstance(provider, ModelProvider)
        self.opener.open.assert_not_called()

    def test_required_configuration_and_key_reference_fail_without_fallback(self) -> None:
        for field in ("model_name", "endpoint", "api_key_env"):
            for value in (None, "", "  "):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ProviderConfigError):
                        create_provider(config(**{field: value}))
        with self.assertRaises(ProviderConfigError):
            create_provider(config(api_key_env="not-a-variable!"))
        with self.assertRaises(ProviderConfigError):
            create_provider("openai-compatible")
        self.opener.open.assert_not_called()

    def test_missing_or_invalid_key_fails_before_network(self) -> None:
        for value in ("", "  ", "contains\r\nheader", "contains space", "非ASCII"):
            with self.subTest(value=value), patch.dict(os.environ, {ENV_NAME: value}):
                with self.assertRaises(MissingAPIKeyError) as raised:
                    create_provider(config())
                self.assertEqual(raised.exception.to_dict()["code"], "missing_api_key")
        self.opener.open.assert_not_called()

    def test_key_is_not_cached_or_part_of_config(self) -> None:
        provider = create_provider(config())
        self.assertNotIn(KEY, repr(provider.__dict__))
        self.assertNotIn(KEY, repr(config()))
        with patch.dict(os.environ, {ENV_NAME: ""}):
            with self.assertRaises(MissingAPIKeyError):
                provider.complete(**TEXT_REQUEST)
        self.opener.open.assert_not_called()

    def test_request_construction_and_single_network_call(self) -> None:
        provider = OpenAICompatibleProvider(config(), timeout=4.5)
        self.assertEqual(provider.complete(**TEXT_REQUEST), {"type": "final_answer", "content": "Hello"})
        self.opener.open.assert_called_once()
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://provider.invalid/v1/chat/completions")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.get_header("Authorization"), "Bearer " + KEY)
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 4.5)
        body = json.loads(request.data)
        self.assertEqual(body["model"], "synthetic-model")
        self.assertFalse(body["stream"])
        self.assertEqual(body["messages"][-1], TEXT_REQUEST["messages"][0])
        self.assertNotIn("tools", body)
        self.assertNotIn(KEY, request.data.decode())

    def test_tools_schema_preserved_without_mutating_inputs(self) -> None:
        request = {"messages": [{"role": "user", "content": "analyze", "dataset_context": {
            "datasets": [{"datasetId": "ds_sales", "columns": [{"name": "销售额", "type": "number"}]}],
        }, "schema": {"columns": ["销售额"]}, "provider_config": "internal-marker"}], "tools": [copy.deepcopy(TOOL)]}
        original = copy.deepcopy(request)
        create_provider(config()).complete(**request)
        self.assertEqual(request, original)
        body = json.loads(self.opener.open.call_args.args[0].data)
        self.assertEqual(body["tools"], [TOOL])
        self.assertEqual(body["tool_choice"], "auto")
        self.assertFalse(body["parallel_tool_calls"])
        remote_user = body["messages"][-1]
        self.assertEqual(set(remote_user), {"role", "content"})
        self.assertIn("ds_sales", remote_user["content"])
        self.assertIn("销售额", remote_user["content"])
        self.assertNotIn("internal-marker", json.dumps(body))

    def test_tool_history_is_valid_chat_completions_input(self) -> None:
        messages = [TEXT_REQUEST["messages"][0], {
            "role": "assistant", "content": None,
            "tool_calls": tool_response()["choices"][0]["message"]["tool_calls"],
        }, {"role": "tool", "tool_call_id": "call-provider-1", "name": "basic_stats",
            "content": '{"ok":true,"data":{"value":1580}}', "private_metadata": "not-an-api-field"}]
        create_provider(config()).complete(messages=messages, tools=[TOOL])
        body = json.loads(self.opener.open.call_args.args[0].data)
        self.assertEqual(body["messages"][-2], messages[-2])
        self.assertEqual(set(body["messages"][-1]), {"role", "tool_call_id", "content"})
        self.assertIn("1580", body["messages"][-1]["content"])

    def test_final_answer_envelope_adaptation(self) -> None:
        self.opener.open.return_value = response(final_response('{"type":"final_answer","content":"结果已完成"}'))
        self.assertEqual(create_provider(config()).complete(**TEXT_REQUEST), {
            "type": "final_answer", "content": "结果已完成",
        })

    def test_needs_user_input_explicit_envelope_not_inferred_from_prose(self) -> None:
        provider = create_provider(config())
        self.opener.open.return_value = response(final_response('{"type":"needs_user_input","content":"请选择指标"}'))
        self.assertEqual(provider.complete(**TEXT_REQUEST), {"type": "needs_user_input", "content": "请选择指标"})
        self.opener.open.return_value = response(final_response("Which column?"))
        self.assertEqual(provider.complete(**TEXT_REQUEST)["type"], "final_answer")

    def test_skill_output_json_remains_final_answer_content(self) -> None:
        content = '{"summary":"done","evidence":[{"evidenceCallId":"call-1"}]}'
        self.opener.open.return_value = response(final_response(content))
        self.assertEqual(create_provider(config()).complete(**TEXT_REQUEST), {"type": "final_answer", "content": content})

    def test_tool_call_adaptation_contains_only_agent_decision(self) -> None:
        self.opener.open.return_value = response(tool_response())
        self.assertEqual(create_provider(config()).complete(messages=TEXT_REQUEST["messages"], tools=[TOOL]), {
            "type": "tool_call", "id": "call-provider-1", "name": "basic_stats", "arguments": {"column": "销售额"},
        })

    def test_invalid_json_and_incomplete_response_fail_safely(self) -> None:
        invalid = [b"not JSON", b"\xff", {}, [], {"error": {"message": KEY}}, {"choices": []},
                   {"choices": [None]}, final_response(" "), final_response('{"type":"needs_user_input","content":2}'),
                   final_response('{"type":"final_answer","content":"ok","extra":"raw"}')]
        for reason in ("length", "content_filter", None, "tool_calls"):
            item = final_response()
            item["choices"][0]["finish_reason"] = reason
            invalid.append(item)
        for value in invalid:
            with self.subTest(value=value):
                self.opener.open.return_value = response(value)
                with self.assertRaises(ProviderInvalidResponseError) as raised:
                    create_provider(config()).complete(**TEXT_REQUEST)
                self.assertIsNone(raised.exception.__context__)
                self.assertNotIn(KEY, str(raised.exception))

    def test_invalid_tool_call_rejected_without_silent_dropping(self) -> None:
        invalid = []
        for arguments in ("[1]", "null", "not JSON", '{"x":NaN}', '{"x":1e999}'):
            invalid.append(tool_response(arguments))
        for value in (None, "", 123):
            item = tool_response()
            item["choices"][0]["message"]["tool_calls"][0]["id"] = value
            invalid.append(item)
        item = tool_response()
        item["choices"][0]["message"]["tool_calls"][0]["function"]["name"] = "not_registered"
        invalid.append(item)
        item = tool_response()
        item["choices"][0]["message"]["tool_calls"] *= 2
        invalid.append(item)
        for calls in ({}, "bad", [None], [{"function": None}]):
            item = tool_response()
            item["choices"][0]["message"]["tool_calls"] = calls
            invalid.append(item)
        for item in invalid:
            with self.subTest(item=item):
                self.opener.open.return_value = response(item)
                with self.assertRaises(ProviderInvalidResponseError):
                    create_provider(config()).complete(messages=TEXT_REQUEST["messages"], tools=[TOOL])

    def test_invalid_input_rejected_before_network(self) -> None:
        for messages, tools in (([], []), ([{"role": "unsupported", "content": "x"}], []),
                                ([{"role": "tool", "content": "x"}], []),
                                ([{"role": "user", "content": 123}], []),
                                ([{"role": "user", "content": "\ud800"}], []),
                                (TEXT_REQUEST["messages"], [{"type": "function", "function": None}]),
                                (TEXT_REQUEST["messages"], [TOOL, TOOL])):
            with self.subTest(messages=messages, tools=tools):
                with self.assertRaises(ProviderRequestError):
                    create_provider(config()).complete(messages=messages, tools=tools)
        self.opener.open.assert_not_called()

    def test_endpoint_validation_and_completion_suffix(self) -> None:
        for endpoint in ("http://provider.invalid/v1", "https://user:password@provider.invalid", "https://provider.invalid?key=x",
                         "https://provider.invalid/#x", "https://provider.invalid:bad", "file:///secret", "https://[bad", "https://provider.invalid/ bad"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ProviderConfigError):
                create_provider(config(endpoint=endpoint))
        for endpoint in ("https://provider.invalid/v1/chat/completions/", "http://127.0.0.1:8080/v1"):
            create_provider(config(endpoint=endpoint)).complete(**TEXT_REQUEST)
            self.assertEqual(self.opener.open.call_args.args[0].full_url, endpoint.rstrip("/") if "chat/completions" in endpoint else endpoint + "/chat/completions")

    def test_invalid_timeout(self) -> None:
        for timeout in (0, -1, float("inf"), float("nan"), True, "30"):
            with self.subTest(timeout=timeout), self.assertRaises(ProviderConfigError):
                OpenAICompatibleProvider(config(), timeout=timeout)

    def test_timeout_direct_wrapped_and_body_read(self) -> None:
        provider = create_provider(config())
        for error in (TimeoutError(KEY), URLError(TimeoutError(KEY))):
            self.opener.open.reset_mock()
            self.opener.open.side_effect = error
            with self.assertRaises(ProviderTimeoutError) as raised:
                provider.complete(**TEXT_REQUEST)
            self.assertIsNone(raised.exception.__context__)
            self.assertEqual(raised.exception.to_dict()["code"], "provider_timeout")
            self.opener.open.assert_called_once()
        self.opener.open.side_effect = None
        mock = response(final_response())
        mock.read.side_effect = TimeoutError(KEY)
        self.opener.open.return_value = mock
        with self.assertRaises(ProviderTimeoutError):
            provider.complete(**TEXT_REQUEST)

    def test_auth_errors_never_read_or_echo_vendor_error_body(self) -> None:
        provider = create_provider(config())
        for status in (401, 403):
            body = MagicMock()
            self.opener.open.side_effect = HTTPError("https://" + KEY, status, KEY, {}, body)
            with self.assertRaises(ProviderAuthenticationError) as raised:
                provider.complete(**TEXT_REQUEST)
            body.read.assert_not_called()
            self.assertIsNone(raised.exception.__context__)
            self.assertNotIn(KEY, "".join(traceback.format_exception(raised.exception)))

    def test_network_and_other_http_errors_have_fixed_messages_and_no_retry(self) -> None:
        provider = create_provider(config())
        for error, expected in ((URLError(KEY), ProviderNetworkError), (OSError(KEY), ProviderNetworkError),
                                (RuntimeError(KEY), ProviderNetworkError),
                                (HTTPError("https://" + KEY, 429, KEY, {}, io.BytesIO(KEY.encode())), ProviderHTTPError),
                                (HTTPError("https://" + KEY, 500, KEY, {}, io.BytesIO(KEY.encode())), ProviderHTTPError)):
            self.opener.open.reset_mock()
            self.opener.open.side_effect = error
            with self.assertRaises(expected) as raised:
                provider.complete(**TEXT_REQUEST)
            self.opener.open.assert_called_once()
            self.assertIsNone(raised.exception.__context__)
            self.assertNotIn(KEY, json.dumps(raised.exception.to_dict()))

    def test_response_size_is_bounded(self) -> None:
        self.opener.open.return_value = response(b" " * 1_048_577)
        with self.assertRaises(ProviderInvalidResponseError):
            create_provider(config()).complete(**TEXT_REQUEST)
        self.opener.open.return_value.read.assert_called_once_with(1_048_577)

    def test_redirect_handler_never_forwards_authorization(self) -> None:
        from providers.openai_compatible import _NoRedirect
        handler = _NoRedirect()
        for code in (301, 302, 303, 307, 308):
            self.assertIsNone(handler.redirect_request(None, None, code, KEY, {}, "https://other.invalid"))
        self.opener.open.side_effect = HTTPError("https://provider.invalid", 302, KEY, {}, io.BytesIO())
        with self.assertRaises(ProviderHTTPError):
            create_provider(config()).complete(**TEXT_REQUEST)

    def test_credential_material_cannot_be_model_input_or_config(self) -> None:
        with self.assertRaises(ProviderConfigError):
            create_provider(config(model_name=KEY))
        with self.assertRaises(ProviderConfigError):
            create_provider(config(endpoint="https://provider.invalid/" + KEY))
        with self.assertRaises(ProviderRequestError):
            create_provider(config()).complete(messages=[{"role": "user", "content": KEY}], tools=[])
        self.opener.open.assert_not_called()

    def test_credential_echo_in_decisions_is_blocked(self) -> None:
        echoed_tool = tool_response(json.dumps({"column": KEY}))
        escaped = "".join("\\u%04x" % ord(c) for c in KEY)
        cases = [(final_response(KEY), []), (final_response('{"type":"needs_user_input","content":"' + escaped + '"}'), []),
                 (echoed_tool, [TOOL])]
        item = tool_response()
        item["choices"][0]["message"]["tool_calls"][0]["id"] = KEY
        cases.append((item, [TOOL]))
        for vendor_response, tools in cases:
            with self.subTest(vendor_response=vendor_response):
                self.opener.open.return_value = response(vendor_response)
                with self.assertRaises(ProviderInvalidResponseError):
                    create_provider(config()).complete(messages=TEXT_REQUEST["messages"], tools=tools)

    def test_json_escaped_credential_is_blocked(self) -> None:
        special_key = 'synthetic-key-with-"quote-and-\\slash'
        with patch.dict(os.environ, {ENV_NAME: special_key}):
            provider = create_provider(config())
            self.opener.open.return_value = response(tool_response(json.dumps({"column": special_key})))
            with self.assertRaises(ProviderInvalidResponseError):
                provider.complete(messages=TEXT_REQUEST["messages"], tools=[TOOL])
            self.opener.open.return_value = response(final_response(json.dumps({"summary": special_key})))
            with self.assertRaises(ProviderInvalidResponseError):
                provider.complete(**TEXT_REQUEST)

    def test_standard_library_http_roundtrip_and_redirect_auth_boundary(self) -> None:
        # Actual local HTTP, never a real model service or remote network dependency.
        self.opener_patch.stop()
        received = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                received.append((self.path, self.headers.get("Authorization"), body))
                if self.path.startswith("/redirect/"):
                    self.send_response(307)
                    self.send_header("Location", "/receiver/chat/completions")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                raw = json.dumps(final_response()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            provider = create_provider(config(endpoint=base + "/v1"))
            self.assertEqual(provider.complete(**TEXT_REQUEST), {"type": "final_answer", "content": "Hello"})
            self.assertEqual(received[0][0], "/v1/chat/completions")
            self.assertEqual(received[0][1], "Bearer " + KEY)
            self.assertNotIn(KEY, json.dumps(received[0][2]))
            redirected = create_provider(config(endpoint=base + "/redirect"))
            with self.assertRaises(ProviderHTTPError):
                redirected.complete(**TEXT_REQUEST)
            self.assertEqual([item[0] for item in received], ["/v1/chat/completions", "/redirect/chat/completions"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_runtime_skill_reuses_real_provider_and_safe_session_trace(self) -> None:
        from desktop.python.runtime_bridge import build_workflow, persist_run
        from session import SQLiteSessionStore
        from skill_runtime.tool_view import build_skill_tool_view

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = SQLiteSessionStore(root / "sessions.sqlite3")
            try:
                store.create_session("thread_provider_real")
                with patch("desktop.python.runtime_bridge.runtime_root", return_value=root):
                    workflow, runner = build_workflow("thread_provider_real", store, {
                        "path": str(ROOT / "tests" / "fixtures" / "sales.csv"), "dataset_id": "ds_provider_sales",
                    }, provider_config=config())
                self.assertIsInstance(runner.loop.model, OpenAICompatibleProvider)
                skills = workflow.nodes["analysis"].skill_runtime
                definition = skills.registry.load("data-diagnosis")
                restricted = build_skill_tool_view(runner.loop.registry, definition.allowed_tools)
                self.assertIs(skills._build_loop(definition, restricted).model, runner.loop.model)
                first = tool_response('{"datasetId":"ds_provider_sales","metric":"销售额","operation":"sum"}')
                self.opener.open.side_effect = [response(first), response(final_response("工具返回销售额总和为 1580。"))]
                result = workflow.invoke({"query": "计算销售额总和"})
                self.assertEqual(result["status"], "ok")
                trace = result["data"]["agent_state"]["execution_trace"]
                self.assertEqual(trace[0]["data"]["value"], 1580)
                persist_run(store, runner, result, thread_id="thread_provider_real", run_id="run_provider_real", query="计算销售额总和",
                            trace_id=result["data"]["observability"]["trace_id"])
                serialized = json.dumps([result, store.get_messages("thread_provider_real"), store.get_events("thread_provider_real")])
                for marker in (KEY, ENV_NAME, config().model_name, config().endpoint, "raw-vendor-id", "total_tokens", "api_key_env", "Authorization"):
                    self.assertNotIn(marker, serialized)
            finally:
                store.close()

    def test_failed_provider_has_no_credential_in_runtime_errors_logs_or_session(self) -> None:
        from desktop.python.runtime_bridge import build_workflow, persist_run
        from session import SQLiteSessionStore

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = SQLiteSessionStore(root / "sessions.sqlite3")
            output, log_output = io.StringIO(), io.StringIO()
            handler = logging.StreamHandler(log_output)
            logging.getLogger().addHandler(handler)
            self.addCleanup(logging.getLogger().removeHandler, handler)
            try:
                for index, failure in enumerate((ProviderInvalidResponseError, ProviderAuthenticationError)):
                    thread_id = f"thread_provider_failure_{index}"
                    store.create_session(thread_id)
                    self.opener.open.side_effect = None
                    with patch("desktop.python.runtime_bridge.runtime_root", return_value=root):
                        workflow, runner = build_workflow(thread_id, store, {
                            "path": str(ROOT / "tests" / "fixtures" / "sales.csv"), "dataset_id": "ds_error_sales",
                        }, provider_config=config())
                    if failure is ProviderInvalidResponseError:
                        self.opener.open.return_value = response(final_response(KEY))
                    else:
                        self.opener.open.side_effect = HTTPError("https://" + KEY, 401, KEY, {}, io.BytesIO(KEY.encode()))
                    with redirect_stdout(output), redirect_stderr(output):
                        result = workflow.invoke({"query": "计算销售额总和"})
                    self.assertEqual(result["status"], "error")
                    persist_run(store, runner, result, thread_id=thread_id, run_id=f"run_failure_{index}", query="计算销售额总和",
                                trace_id=result["data"]["observability"]["trace_id"])
                    serialized = json.dumps([result, store.get_messages(thread_id), store.get_events(thread_id)], ensure_ascii=False)
                    for marker in (KEY, ENV_NAME, config().endpoint, "Authorization"):
                        self.assertNotIn(marker, serialized + output.getvalue() + log_output.getvalue())
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
