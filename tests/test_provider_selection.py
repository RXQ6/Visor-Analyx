from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from providers import (
    DeterministicModelProvider, MissingAPIKeyError, OpenAICompatibleProvider,
    ProviderConfig, ProviderConfigError, UnknownProviderError,
    create_provider, load_provider_config,
)


ROOT = Path(__file__).resolve().parents[1]
MODE_ENV = (
    "DATA_AGENT_PROVIDER_ID", "DATA_AGENT_MODEL_NAME",
    "DATA_AGENT_PROVIDER_ENDPOINT", "DATA_AGENT_API_KEY_ENV",
)
TIMEOUT_ENV = "DATA_AGENT_PROVIDER_TIMEOUT_SECONDS"
KEY_ENV = "PHASE24_SYNTHETIC_API_KEY"
KEY = "synthetic-phase24-not-a-real-credential"
REAL_ENV = {
    "DATA_AGENT_PROVIDER_ID": "openai-compatible",
    "DATA_AGENT_MODEL_NAME": "phase24-synthetic-model",
    "DATA_AGENT_PROVIDER_ENDPOINT": "https://phase24.invalid/v1",
    "DATA_AGENT_API_KEY_ENV": KEY_ENV,
}


def final_response() -> dict:
    return {"usage": {"total_tokens": 123}, "choices": [{
        "finish_reason": "stop", "message": {
            "role": "assistant", "content": "工具返回销售额总和为 1580。",
        },
    }]}


def tool_response() -> dict:
    return {"choices": [{"finish_reason": "tool_calls", "message": {
        "role": "assistant", "content": None, "tool_calls": [{
            "id": "call-phase24", "type": "function", "function": {
                "name": "basic_stats", "arguments": json.dumps({
                    "datasetId": "ds_phase24_sales", "metric": "销售额", "operation": "sum",
                }),
            },
        }],
    }}]}


def http_response(body: dict) -> MagicMock:
    response = MagicMock()
    response.__enter__.return_value = response
    response.status = 200
    response.read.return_value = json.dumps(body).encode("utf-8")
    return response


def command() -> dict:
    return {
        "protocol_version": 1, "type": "run.start", "request_id": "req_phase24",
        "run_id": "run_phase24", "thread_id": "thread_phase24",
        "payload": {"message": "计算销售额总和"},
        "_dataset": {
            "path": str(ROOT / "tests" / "fixtures" / "sales.csv"),
            "dataset_id": "ds_phase24_sales",
        },
    }


class ProviderSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        # Restore the developer's environment afterward; never inspect real keys.
        environment = patch.dict(os.environ, {KEY_ENV: KEY, "DESKTOP_BRIDGE_WORKER_DELAY_MS": "0"})
        environment.start()
        self.addCleanup(environment.stop)
        for name in (*MODE_ENV, TIMEOUT_ENV):
            os.environ.pop(name, None)
        opener_patch = patch("providers.openai_compatible.build_opener")
        self.opener = opener_patch.start().return_value
        self.addCleanup(opener_patch.stop)
        self.opener.open.return_value = http_response(final_response())

    def assert_safe(self, serialized: str, *, endpoint: str | None = None) -> None:
        for marker in (
            KEY, KEY_ENV, REAL_ENV["DATA_AGENT_MODEL_NAME"],
            endpoint or REAL_ENV["DATA_AGENT_PROVIDER_ENDPOINT"],
            '"api_key_env"', '"provider_config"', '"provider_id"', '"model_name"',
            '"endpoint"', "Authorization", "total_tokens", *MODE_ENV,
        ):
            self.assertNotIn(marker, serialized)

    def run_worker(self) -> tuple[int, list[dict], str, list, list]:
        from desktop.python import runtime_bridge as bridge
        from session import SQLiteSessionStore

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, errors = io.StringIO(), io.StringIO()
            with patch.object(bridge, "runtime_root", return_value=root):
                with redirect_stdout(output), redirect_stderr(errors):
                    exit_code = bridge.worker(command())
            frames = [json.loads(line) for line in output.getvalue().splitlines()]
            with SQLiteSessionStore(root / "sessions.sqlite3") as store:
                messages = store.get_messages("thread_phase24")
                events = store.get_events("thread_phase24")
            self.assert_safe(output.getvalue() + errors.getvalue() + json.dumps([messages, events]))
            # The existing Runtime Event envelope is preserved.
            for frame in frames:
                self.assertEqual(set(frame), {
                    "protocol_version", "request_id", "run_id", "thread_id", "trace_id",
                    "sequence", "type", "payload", "error",
                })
            return exit_code, frames, errors.getvalue(), messages, events

    def test_default_reads_only_selector_and_no_files_or_credentials(self) -> None:
        reads = []

        class SelectionOnly(dict):
            def get(self, name, default=None):
                reads.append(name)
                if name != "DATA_AGENT_PROVIDER_ID":
                    raise AssertionError("default accessed an optional field or credential")
                return super().get(name, default)

        with patch("builtins.open", side_effect=AssertionError("unexpected config file read")):
            config = load_provider_config(SelectionOnly())
        self.assertEqual(reads, ["DATA_AGENT_PROVIDER_ID"])
        self.assertEqual(config, ProviderConfig())
        self.assertIsInstance(create_provider(config), DeterministicModelProvider)
        self.opener.open.assert_not_called()

    def test_optional_metadata_does_not_implicitly_enable_real_mode(self) -> None:
        source = {name: value for name, value in REAL_ENV.items() if name != MODE_ENV[0]}
        config = load_provider_config(source)
        self.assertEqual(config, ProviderConfig())
        self.assertIsInstance(create_provider(config), DeterministicModelProvider)

    def test_explicit_deterministic_does_not_read_credentials(self) -> None:
        source = {**REAL_ENV, MODE_ENV[0]: "deterministic"}
        with patch("providers.openai_compatible.os.environ.get", side_effect=AssertionError("unexpected key read")):
            provider = create_provider(load_provider_config(source))
        self.assertIsInstance(provider, DeterministicModelProvider)

    def test_explicit_real_configuration_creates_correct_instance_without_calling_network(self) -> None:
        reads = []

        class MetadataOnly(dict):
            def get(self, name, default=None):
                reads.append(name)
                if name not in (*MODE_ENV, TIMEOUT_ENV):
                    raise AssertionError("loader read credential value")
                return super().get(name, default)

        config = load_provider_config(MetadataOnly(REAL_ENV))
        self.assertEqual(set(reads), {*MODE_ENV, TIMEOUT_ENV})
        self.assertEqual(config.provider_id, "openai-compatible")
        self.assertEqual(config.api_key_env, KEY_ENV)
        self.assertIsInstance(create_provider(config), OpenAICompatibleProvider)
        self.opener.open.assert_not_called()

    def test_empty_selector_is_an_error_not_a_default(self) -> None:
        for value in ("", "  "):
            with self.subTest(value=value), self.assertRaises(ProviderConfigError):
                load_provider_config({MODE_ENV[0]: value})

    def test_missing_real_fields_fail_without_constructing_deterministic(self) -> None:
        for name in MODE_ENV[1:]:
            for value in (None, "", "  "):
                source = dict(REAL_ENV)
                if value is None:
                    source.pop(name)
                else:
                    source[name] = value
                with self.subTest(name=name, value=value):
                    with patch("providers.factory.DeterministicModelProvider") as fallback:
                        with self.assertRaises(ProviderConfigError) as raised:
                            create_provider(load_provider_config(source))
                        self.assertEqual(raised.exception.to_dict()["code"], "invalid_provider_config")
                        fallback.assert_not_called()
        self.opener.open.assert_not_called()

    def test_missing_credential_fails_without_fallback(self) -> None:
        os.environ.pop(KEY_ENV)
        with patch("providers.factory.DeterministicModelProvider") as fallback:
            with self.assertRaises(MissingAPIKeyError) as raised:
                create_provider(load_provider_config(REAL_ENV))
            self.assertEqual(raised.exception.to_dict()["code"], "missing_api_key")
            fallback.assert_not_called()
        self.opener.open.assert_not_called()

    def test_unknown_and_reserved_selectors_fail_with_safe_error(self) -> None:
        for selected in ("openai", "anthropic", "gemini", "local", "unknown-" + KEY):
            with self.subTest(selected=selected):
                with self.assertRaises(UnknownProviderError) as raised:
                    create_provider(load_provider_config({MODE_ENV[0]: selected}))
                self.assertEqual(raised.exception.to_dict()["code"], "unsupported_provider")
                self.assertNotIn(selected, str(raised.exception))
                self.assertNotIn(KEY, json.dumps(raised.exception.to_dict()))
        self.opener.open.assert_not_called()

    def test_factory_no_arguments_stays_deterministic_independent_of_environment(self) -> None:
        with patch.dict(os.environ, REAL_ENV):
            with patch("providers.openai_compatible.os.environ.get", side_effect=AssertionError("unexpected key read")):
                self.assertIsInstance(create_provider(), DeterministicModelProvider)

    def test_both_selections_preserve_same_instance_in_skill_loop(self) -> None:
        from desktop.python.runtime_bridge import build_workflow
        from session import SQLiteSessionStore
        from skill_runtime.tool_view import build_skill_tool_view

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with SQLiteSessionStore(root / "sessions.sqlite3") as store:
                for index, source in enumerate(({}, REAL_ENV)):
                    thread_id = f"thread_selection_skill_{index}"
                    store.create_session(thread_id)
                    with patch("desktop.python.runtime_bridge.runtime_root", return_value=root):
                        workflow, runner = build_workflow(
                            thread_id, store, provider_config=load_provider_config(source),
                        )
                    expected = DeterministicModelProvider if index == 0 else OpenAICompatibleProvider
                    self.assertIsInstance(runner.loop.model, expected)
                    skill = workflow.nodes["analysis"].skill_runtime
                    definition = skill.registry.load("data-diagnosis")
                    view = build_skill_tool_view(runner.loop.registry, definition.allowed_tools)
                    self.assertIs(skill._build_loop(definition, view).model, runner.loop.model)
        self.opener.open.assert_not_called()

    def test_worker_default_and_explicit_deterministic_preserve_original_result(self) -> None:
        replies = []
        for source in ({}, {MODE_ENV[0]: "deterministic"}):
            with patch.dict(os.environ, source):
                exit_code, frames, _, messages, events = self.run_worker()
            self.assertEqual(exit_code, 0)
            self.assertEqual(frames[-1]["type"], "run_completed")
            self.assertIn("1580", frames[-1]["payload"]["response"])
            self.assertTrue(messages)
            self.assertTrue(events)
            replies.append(frames[-1]["payload"])
        self.assertEqual(replies[0], replies[1])
        self.opener.open.assert_not_called()

    def test_worker_real_uses_network_adapter_and_deterministic_tool_without_config_leak(self) -> None:
        self.opener.open.side_effect = [http_response(tool_response()), http_response(final_response())]
        with patch.dict(os.environ, REAL_ENV):
            exit_code, frames, _, messages, events = self.run_worker()
        self.assertEqual(exit_code, 0)
        self.assertEqual(frames[-1]["type"], "run_completed")
        self.assertIn("1580", frames[-1]["payload"]["response"])
        self.assertEqual(self.opener.open.call_count, 2)
        self.assertTrue(messages)
        self.assertTrue(events)
        body = json.loads(self.opener.open.call_args_list[1].args[0].data)
        observations = [item for item in body["messages"] if item["role"] == "tool"]
        self.assertEqual(json.loads(observations[0]["content"])["data"]["value"], 1580)

    def test_worker_configuration_failures_emit_safe_structured_errors_without_fallback(self) -> None:
        cases = (
            ({MODE_ENV[0]: ""}, "invalid_provider_config"),
            ({MODE_ENV[0]: "openai-compatible"}, "invalid_provider_config"),
            (REAL_ENV, "missing_api_key"),
            ({MODE_ENV[0]: "unknown-" + KEY}, "unsupported_provider"),
        )
        os.environ.pop(KEY_ENV)
        for source, code in cases:
            with self.subTest(code=code), patch.dict(os.environ, source):
                with patch("providers.factory.DeterministicModelProvider") as fallback:
                    with patch("desktop.python.runtime_bridge.DatasetRegistry") as datasets:
                        exit_code, frames, _, messages, events = self.run_worker()
                    fallback.assert_not_called()
                    datasets.assert_not_called()
                self.assertEqual(exit_code, 1)
                self.assertEqual([frame["type"] for frame in frames], ["run_started", "run_failed"])
                self.assertEqual(frames[-1]["error"]["code"], code)
                self.assertEqual(messages, [])
                self.assertEqual(events, [])
        self.opener.open.assert_not_called()

    def test_worker_auth_failure_does_not_fallback_or_leak_vendor_error(self) -> None:
        self.opener.open.side_effect = HTTPError(
            "https://" + KEY, 401, KEY, {}, io.BytesIO(KEY.encode()),
        )
        with patch.dict(os.environ, REAL_ENV):
            with patch("providers.factory.DeterministicModelProvider") as fallback:
                exit_code, frames, _, _, _ = self.run_worker()
                fallback.assert_not_called()
        self.assertEqual(exit_code, 1)
        self.assertEqual(frames[-1]["type"], "run_failed")
        self.assertEqual(self.opener.open.call_count, 1)

    def test_child_runtime_reads_inherited_real_selection_with_local_http_only(self) -> None:
        from session import SQLiteSessionStore

        calls = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args) -> None:
                pass

            def do_POST(self) -> None:
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                calls.append(body)
                raw = json.dumps(tool_response() if len(calls) == 1 else final_response()).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        endpoint = f"http://127.0.0.1:{server.server_port}/v1"
        try:
            with tempfile.TemporaryDirectory() as directory:
                environment = {
                    **os.environ, **REAL_ENV, "DATA_AGENT_PROVIDER_ENDPOINT": endpoint,
                    "DATA_AGENT_RUNTIME_DIR": directory, "PYTHONIOENCODING": "utf-8",
                    "PYTHONUTF8": "1", "NO_PROXY": "127.0.0.1",
                }
                result = subprocess.run(
                    [sys.executable, "-B", str(ROOT / "desktop" / "python" / "runtime_bridge.py"), "--worker"],
                    input=json.dumps(command()), text=True, encoding="utf-8", capture_output=True,
                    cwd=ROOT, env=environment, timeout=30,
                )
                self.assertEqual(result.returncode, 0, "child runtime did not complete")
                frames = [json.loads(line) for line in result.stdout.splitlines()]
                self.assertEqual(frames[-1]["type"], "run_completed")
                self.assertEqual(len(calls), 2)
                self.assertEqual(calls[0]["model"], REAL_ENV["DATA_AGENT_MODEL_NAME"])
                observation = next(item for item in calls[1]["messages"] if item["role"] == "tool")
                self.assertEqual(json.loads(observation["content"])["data"]["value"], 1580)
                with SQLiteSessionStore(Path(directory) / "sessions.sqlite3") as store:
                    records = [store.get_messages("thread_phase24"), store.get_events("thread_phase24")]
                self.assert_safe(result.stdout + result.stderr + json.dumps(records), endpoint=endpoint)
                self.assertNotIn(KEY, json.dumps(calls))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
