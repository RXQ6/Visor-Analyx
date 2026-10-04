from __future__ import annotations

import io
import json
import os
import tempfile
import traceback
import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import FrozenInstanceError
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from providers import (
    DeterministicModelProvider, MissingAPIKeyError, OpenAICompatibleProvider,
    ProviderAuthenticationError, ProviderConfig, ProviderConfigError, ProviderHTTPError,
    ProviderInvalidResponseError, ProviderNetworkError, ProviderObservations,
    ProviderRateLimitedError, ProviderRequestError, ProviderTimeoutError,
    ProviderUnavailableError, classify_provider_error, create_provider, load_provider_config,
)


KEY = "synthetic-phase25-never-a-real-key"
KEY_ENV = "PHASE25_SYNTHETIC_API_KEY"
ENDPOINT = "https://phase25.invalid/v1"
MODEL = "phase25-synthetic-model"
TIMEOUT_ENV = "DATA_AGENT_PROVIDER_TIMEOUT_SECONDS"
TEXT = {"messages": [{"role": "user", "content": "phase25-private-prompt"}], "tools": []}


def config(**values) -> ProviderConfig:
    return ProviderConfig(**{
        "provider_id": "openai-compatible", "model_name": MODEL,
        "endpoint": ENDPOINT, "api_key_env": KEY_ENV, **values,
    })


def body(*, content: str = "phase25-private-response", **extra) -> dict:
    return {"id": "chatcmpl-not-a-request-id", "choices": [{
        "finish_reason": "stop", "message": {"role": "assistant", "content": content},
    }], **extra}


def response(payload: dict | bytes, *, status: int = 200, request_id: str | None = None) -> MagicMock:
    result = MagicMock()
    result.__enter__.return_value = result
    result.status = status
    result.headers = {} if request_id is None else {"x-request-id": request_id}
    result.read.return_value = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return result


class ProviderReliabilityTests(unittest.TestCase):
    def setUp(self) -> None:
        environment = patch.dict(os.environ, {KEY_ENV: KEY, "DESKTOP_BRIDGE_WORKER_DELAY_MS": "0"})
        environment.start()
        self.addCleanup(environment.stop)
        for name in (
            "DATA_AGENT_PROVIDER_ID", "DATA_AGENT_MODEL_NAME",
            "DATA_AGENT_PROVIDER_ENDPOINT", "DATA_AGENT_API_KEY_ENV", TIMEOUT_ENV,
        ):
            os.environ.pop(name, None)
        opener_patch = patch("providers.openai_compatible.build_opener")
        self.opener = opener_patch.start().return_value
        self.addCleanup(opener_patch.stop)
        self.opener.open.return_value = response(body())

    def assert_safe(self, serialized: str) -> None:
        for marker in (KEY, KEY_ENV, ENDPOINT, "Authorization", "Bearer", "phase25-private-prompt", "phase25-private-response"):
            self.assertNotIn(marker, serialized)

    def test_six_categories_preserve_existing_error_envelopes(self) -> None:
        errors = (
            (ProviderAuthenticationError(), "auth_error"),
            (ProviderRateLimitedError(), "rate_limited"),
            (ProviderTimeoutError(), "timeout"),
            (ProviderNetworkError(), "network_error"),
            (ProviderInvalidResponseError(), "invalid_response"),
            (ProviderUnavailableError(), "provider_unavailable"),
        )
        self.assertEqual(len({category for _, category in errors}), 6)
        for error, category in errors:
            self.assertEqual(classify_provider_error(error), category)
            self.assertEqual(set(error.to_dict()), {"code", "message"})
        self.assertEqual(ProviderTimeoutError().to_dict()["code"], "provider_timeout")
        self.assertIsInstance(ProviderRateLimitedError(), ProviderHTTPError)
        self.assertIsInstance(ProviderUnavailableError(), ProviderHTTPError)
        self.assertEqual(classify_provider_error(MissingAPIKeyError()), "auth_error")
        self.assertIsNone(classify_provider_error(ProviderRequestError()))

    def test_default_configured_and_constructor_timeouts_reach_transport(self) -> None:
        for selected, expected in ((config(), 30.0), (config(timeout_seconds=0.25), 0.25), (config(timeout_seconds=120), 120)):
            with self.subTest(timeout=expected):
                self.opener.open.reset_mock()
                create_provider(selected).complete(**TEXT)
                self.assertEqual(self.opener.open.call_args.kwargs["timeout"], expected)
        OpenAICompatibleProvider(config(timeout_seconds=100), timeout=2).complete(**TEXT)
        self.assertEqual(self.opener.open.call_args.kwargs["timeout"], 2)

    def test_invalid_timeouts_fail_not_clamp_or_fallback(self) -> None:
        for value in (0, -1, 120.001, float("inf"), float("nan"), True, "30", None):
            with self.subTest(value=value), self.assertRaises(ProviderConfigError):
                config(timeout_seconds=value)
        for value in (0, 121, float("inf"), True):
            with self.subTest(override=value), self.assertRaises(ProviderConfigError):
                OpenAICompatibleProvider(config(), timeout=value)
        self.opener.open.assert_not_called()

    def test_runtime_environment_timeout_parsing_and_safe_errors(self) -> None:
        environment = {
            "DATA_AGENT_PROVIDER_ID": "openai-compatible", "DATA_AGENT_MODEL_NAME": MODEL,
            "DATA_AGENT_PROVIDER_ENDPOINT": ENDPOINT, "DATA_AGENT_API_KEY_ENV": KEY_ENV,
        }
        self.assertEqual(load_provider_config(environment).timeout_seconds, 30)
        self.assertEqual(load_provider_config({**environment, TIMEOUT_ENV: "2.5"}).timeout_seconds, 2.5)
        for value in ("", "0", "121", "nan", "inf", KEY):
            with self.subTest(value=value), self.assertRaises(ProviderConfigError) as raised:
                load_provider_config({**environment, TIMEOUT_ENV: value})
            self.assertIsNone(raised.exception.__context__)
            self.assert_safe("".join(traceback.format_exception(raised.exception)))

    def test_deterministic_ignores_timeout_env_and_retains_original_behavior(self) -> None:
        source = {"DATA_AGENT_PROVIDER_ID": "deterministic", TIMEOUT_ENV: KEY}
        provider = create_provider(load_provider_config(source))
        self.assertIsInstance(provider, DeterministicModelProvider)
        self.assertEqual(provider.complete(**TEXT), {"type": "final_answer", "content": "Desktop Runtime 已完成本次请求。"})
        self.assertFalse(hasattr(provider, "observations"))
        self.opener.open.assert_not_called()

    def test_timeout_direct_wrapped_and_body_read_are_observed_once(self) -> None:
        for failure in (TimeoutError(KEY), URLError(TimeoutError(KEY)), "body"):
            with self.subTest(kind=type(failure).__name__):
                provider = create_provider(config())
                self.opener.open.reset_mock()
                self.opener.open.side_effect = None
                if failure == "body":
                    result = response(body(), request_id="req_phase25_read")
                    result.read.side_effect = TimeoutError(KEY)
                    self.opener.open.return_value = result
                else:
                    self.opener.open.side_effect = failure
                with self.assertRaises(ProviderTimeoutError) as raised:
                    provider.complete(**TEXT)
                self.assertIsNone(raised.exception.__context__)
                metadata, = provider.observations.snapshot()
                self.assertEqual(metadata.error_category, "timeout")
                self.assertIsNone(metadata.input_tokens)
                self.assertGreaterEqual(metadata.latency_ms, 0)
                self.opener.open.assert_called_once()
                self.assert_safe(json.dumps(metadata.to_dict()) + str(raised.exception))

    def test_auth_401_403_never_read_vendor_body(self) -> None:
        for status in (401, 403):
            with self.subTest(status=status):
                provider = create_provider(config())
                vendor_body = MagicMock()
                self.opener.open.reset_mock()
                self.opener.open.side_effect = HTTPError(
                    "https://" + KEY, status, KEY, {"x-request-id": f"req_phase25_auth_{status}", "Authorization": KEY}, vendor_body,
                )
                with self.assertRaises(ProviderAuthenticationError) as raised:
                    provider.complete(**TEXT)
                vendor_body.read.assert_not_called()
                metadata, = provider.observations.snapshot()
                self.assertEqual(metadata.error_category, "auth_error")
                self.assertEqual(metadata.request_id, f"req_phase25_auth_{status}")
                self.opener.open.assert_called_once()
                self.assert_safe(json.dumps(metadata.to_dict()) + "".join(traceback.format_exception(raised.exception)))

    def test_429_exception_and_status_classify_rate_limit_without_retry(self) -> None:
        for is_exception in (True, False):
            with self.subTest(exception=is_exception):
                provider = create_provider(config())
                self.opener.open.reset_mock()
                vendor_body = MagicMock()
                self.opener.open.side_effect = HTTPError(
                    ENDPOINT, 429, KEY, {"x-request-id": "req_phase25_429", "Retry-After": "0"}, vendor_body,
                ) if is_exception else None
                rejected = response(body(usage={"prompt_tokens": 999}), status=429, request_id="req_phase25_429")
                self.opener.open.return_value = rejected
                with self.assertRaises(ProviderRateLimitedError) as raised:
                    provider.complete(**TEXT)
                self.assertEqual(raised.exception.to_dict()["code"], "provider_rate_limited")
                self.assertIsNone(raised.exception.__context__)
                metadata, = provider.observations.snapshot()
                self.assertEqual(metadata.error_category, "rate_limited")
                self.assertEqual(metadata.request_id, "req_phase25_429")
                self.assertIsNone(metadata.input_tokens)
                vendor_body.read.assert_not_called()
                rejected.read.assert_not_called()
                self.opener.open.assert_called_once()

    def test_5xx_classify_unavailable_without_body_or_retry(self) -> None:
        for status in (500, 502, 503, 504, 599):
            for is_exception in (True, False):
                with self.subTest(status=status, exception=is_exception):
                    provider = create_provider(config())
                    self.opener.open.reset_mock()
                    self.opener.open.side_effect = HTTPError(ENDPOINT, status, KEY, {}, io.BytesIO(KEY.encode())) if is_exception else None
                    rejected = response(body(), status=status)
                    self.opener.open.return_value = rejected
                    with self.assertRaises(ProviderUnavailableError):
                        provider.complete(**TEXT)
                    metadata, = provider.observations.snapshot()
                    self.assertEqual(metadata.error_category, "provider_unavailable")
                    self.opener.open.assert_called_once()
                    rejected.read.assert_not_called()

    def test_network_errors_have_safe_metadata_and_no_retry(self) -> None:
        for failure in (URLError(KEY), OSError(KEY)):
            provider = create_provider(config())
            self.opener.open.reset_mock()
            self.opener.open.side_effect = failure
            with self.assertRaises(ProviderNetworkError):
                provider.complete(**TEXT)
            metadata, = provider.observations.snapshot()
            self.assertEqual(metadata.error_category, "network_error")
            self.assertIsNone(metadata.request_id)
            self.assert_safe(json.dumps(metadata.to_dict()))
            self.opener.open.assert_called_once()

    def test_malformed_response_has_safe_failure_metadata(self) -> None:
        for malformed in (KEY.encode(), b"\xff", {"choices": []}, body(content=KEY)):
            provider = create_provider(config())
            self.opener.open.return_value = response(malformed, request_id="req_phase25_bad")
            with self.assertRaises(ProviderInvalidResponseError):
                provider.complete(**TEXT)
            metadata, = provider.observations.snapshot()
            self.assertEqual(metadata.error_category, "invalid_response")
            self.assertEqual(metadata.request_id, "req_phase25_bad")
            self.assertIsNone(metadata.input_tokens)
            self.assert_safe(json.dumps(metadata.to_dict()))

    def test_success_usage_metadata_does_not_change_decision(self) -> None:
        self.opener.open.return_value = response(body(usage={
            "prompt_tokens": 17, "completion_tokens": 4, "total_tokens": 21,
            "prompt_tokens_details": {"secret": KEY}, "unexpected": KEY,
        }), request_id="req_phase25_usage")
        provider = create_provider(config())
        decision = provider.complete(**TEXT)
        self.assertEqual(decision, {"type": "final_answer", "content": "phase25-private-response"})
        metadata, = provider.observations.snapshot()
        self.assertEqual(metadata.provider_id, "openai-compatible")
        self.assertEqual(metadata.model_name, MODEL)
        self.assertEqual((metadata.input_tokens, metadata.output_tokens), (17, 4))
        self.assertIsNone(metadata.error_category)
        self.assertIsNone(metadata.error_code)
        self.assertEqual(set(metadata.to_dict()), {
            "provider_id", "model_name", "latency_ms", "input_tokens", "output_tokens",
            "request_id", "error_category", "error_code",
        })
        self.assert_safe(json.dumps(metadata.to_dict()))

    def test_missing_and_invalid_usage_is_not_guessed_or_coerced(self) -> None:
        for usage in (None, {}, KEY, {"prompt_tokens": True, "completion_tokens": "8"},
                      {"prompt_tokens": -1, "completion_tokens": 3.5},
                      {"prompt_tokens": 2**63, "completion_tokens": KEY}):
            provider = create_provider(config())
            self.opener.open.return_value = response(body(usage=usage))
            provider.complete(**TEXT)
            metadata, = provider.observations.snapshot()
            self.assertIsNone(metadata.input_tokens)
            self.assertIsNone(metadata.output_tokens)
        provider = create_provider(config())
        self.opener.open.return_value = response(body(usage={"prompt_tokens": 0, "completion_tokens": 2}))
        provider.complete(**TEXT)
        self.assertEqual(provider.observations.snapshot()[0].input_tokens, 0)

    def test_latency_uses_monotonic_clock_on_success_and_failure(self) -> None:
        provider = create_provider(config())
        with patch("providers.openai_compatible.time.perf_counter", side_effect=[100, 100.125]):
            provider.complete(**TEXT)
        self.assertEqual(provider.observations.snapshot()[0].latency_ms, 125.0)
        self.opener.open.side_effect = TimeoutError(KEY)
        with patch("providers.openai_compatible.time.perf_counter", side_effect=[200, 200.375]):
            with self.assertRaises(ProviderTimeoutError):
                provider.complete(**TEXT)
        self.assertEqual(provider.observations.snapshot()[1].latency_ms, 375.0)

    def test_request_id_header_precedence_body_fallback_and_no_completion_id_guess(self) -> None:
        cases = (
            (body(request_id="req_body"), "req_header", "req_header"),
            (body(request_id="req_body"), None, "req_body"),
            (body(), None, None),
        )
        for payload, header, expected in cases:
            provider = create_provider(config())
            self.opener.open.return_value = response(payload, request_id=header)
            provider.complete(**TEXT)
            self.assertEqual(provider.observations.snapshot()[0].request_id, expected)

    def test_request_id_untrusted_or_sensitive_values_are_discarded(self) -> None:
        for value in (KEY, "req_" + KEY, KEY_ENV, ENDPOINT, "Authorization", "Bearer", "phase25-private-prompt",
                      "phase25-private-response", "req\nspoof", "req space", "x" * 129, {"raw": KEY}):
            provider = create_provider(config())
            self.opener.open.return_value = response(body(request_id=value, unrelated={"secret": KEY}))
            provider.complete(**TEXT)
            metadata, = provider.observations.snapshot()
            self.assertIsNone(metadata.request_id)
            self.assert_safe(json.dumps(metadata.to_dict()))
        provider = create_provider(config())
        self.opener.open.return_value = response(body(), request_id="req_" + KEY)
        provider.complete(**TEXT)
        self.assertIsNone(provider.observations.snapshot()[0].request_id)

    def test_unsafe_model_identifier_is_redacted_from_observation(self) -> None:
        for model_name in (ENDPOINT, "private model description", "sk-placeholder-not-a-key"):
            provider = create_provider(config(model_name=model_name))
            provider.complete(**TEXT)
            self.assertIsNone(provider.observations.snapshot()[0].model_name)

    def test_observation_sink_failure_does_not_override_result_or_error(self) -> None:
        store = ProviderObservations()
        provider = OpenAICompatibleProvider(config(), observations=store)
        with patch.object(store, "record", side_effect=RuntimeError(KEY)):
            output = io.StringIO()
            with redirect_stdout(output), redirect_stderr(output):
                self.assertEqual(provider.complete(**TEXT)["type"], "final_answer")
                self.opener.open.side_effect = HTTPError(ENDPOINT, 429, KEY, {}, io.BytesIO())
                with self.assertRaises(ProviderRateLimitedError) as raised:
                    provider.complete(**TEXT)
            self.assertIsNone(raised.exception.__context__)
            self.assertEqual(output.getvalue(), "")

    def test_observations_are_bounded_immutable_snapshots(self) -> None:
        store = ProviderObservations(capacity=2)
        provider = OpenAICompatibleProvider(config(), observations=store)
        for index in range(3):
            self.opener.open.return_value = response(body(), request_id=f"req_phase25_{index}")
            provider.complete(**TEXT)
        snapshot = store.snapshot()
        self.assertEqual([item.request_id for item in snapshot], ["req_phase25_1", "req_phase25_2"])
        with self.assertRaises(FrozenInstanceError):
            snapshot[0].model_name = KEY
        copied = snapshot[0].to_dict()
        copied["model_name"] = KEY
        self.assertEqual(store.snapshot()[0].model_name, MODEL)
        for capacity in (0, 257, True, "2"):
            with self.assertRaises(ValueError):
                ProviderObservations(capacity=capacity)

    def test_missing_rotated_credential_is_safe_observed_preflight_failure(self) -> None:
        provider = create_provider(config())
        os.environ.pop(KEY_ENV)
        with self.assertRaises(MissingAPIKeyError):
            provider.complete(**TEXT)
        metadata, = provider.observations.snapshot()
        self.assertEqual(metadata.error_code, "missing_api_key")
        self.assertEqual(metadata.error_category, "auth_error")
        self.assert_safe(json.dumps(metadata.to_dict()))
        self.opener.open.assert_not_called()

    def test_local_sensitive_input_rejection_never_records_prompt(self) -> None:
        provider = create_provider(config())
        with self.assertRaises(ProviderRequestError):
            provider.complete(messages=[{"role": "user", "content": KEY}], tools=[])
        metadata, = provider.observations.snapshot()
        self.assertEqual(metadata.error_code, "provider_invalid_request")
        self.assertIsNone(metadata.error_category)
        self.assert_safe(json.dumps(metadata.to_dict()))
        self.opener.open.assert_not_called()

    def test_runtime_metadata_stays_out_of_session_trace_events_and_logs(self) -> None:
        from desktop.python import runtime_bridge as bridge
        from session import SQLiteSessionStore
        from tests.test_provider_selection import command, tool_response, final_response

        first, last = tool_response(), final_response()
        first["usage"] = {"prompt_tokens": 31, "completion_tokens": 5}
        last["usage"] = {"prompt_tokens": 44, "completion_tokens": 7}
        self.opener.open.side_effect = [
            response(first, request_id="req_phase25_service_1"),
            response(last, request_id="req_phase25_service_2"),
        ]
        provider = create_provider(config())
        environment = {
            "DATA_AGENT_PROVIDER_ID": "openai-compatible", "DATA_AGENT_MODEL_NAME": MODEL,
            "DATA_AGENT_PROVIDER_ENDPOINT": ENDPOINT, "DATA_AGENT_API_KEY_ENV": KEY_ENV,
            TIMEOUT_ENV: "2.5",
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output, errors = io.StringIO(), io.StringIO()
            with patch.dict(os.environ, environment), patch.object(bridge, "runtime_root", return_value=root):
                with patch.object(bridge, "create_provider", return_value=provider) as factory:
                    with redirect_stdout(output), redirect_stderr(errors):
                        code = bridge.worker(command())
                    self.assertEqual(factory.call_args.args[0].timeout_seconds, 2.5)
            self.assertEqual(code, 0)
            frames = [json.loads(line) for line in output.getvalue().splitlines()]
            self.assertEqual(frames[-1]["type"], "run_completed")
            self.assertIn("1580", frames[-1]["payload"]["response"])
            with SQLiteSessionStore(root / "sessions.sqlite3") as store:
                records = [store.get_messages("thread_phase24"), store.get_events("thread_phase24")]
            serialized = output.getvalue() + errors.getvalue() + json.dumps(records)
            self.assert_safe(serialized)
            for marker in (MODEL, "req_phase25_service_1", "req_phase25_service_2", '"input_tokens"', '"output_tokens"', '"provider_id"'):
                self.assertNotIn(marker, serialized)
        metadata = provider.observations.snapshot()
        self.assertEqual(len(metadata), 2)
        self.assertEqual([(item.input_tokens, item.output_tokens) for item in metadata], [(31, 5), (44, 7)])
        self.assertEqual([item.request_id for item in metadata], ["req_phase25_service_1", "req_phase25_service_2"])


if __name__ == "__main__":
    unittest.main()
