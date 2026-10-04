from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from unittest.mock import patch

from providers import (
    DeterministicModelProvider,
    ProviderConfig,
    ProviderConfigError,
    RESERVED_PROVIDER_IDS,
    UnknownProviderError,
    create_provider,
)


ROOT = Path(__file__).resolve().parents[1]


class ProviderConfigTests(unittest.TestCase):
    def test_default_config_creates_deterministic(self) -> None:
        config = ProviderConfig()
        self.assertEqual(config.provider_id, "deterministic")
        self.assertIsNone(config.model_name)
        self.assertIsNone(config.endpoint)
        self.assertIsInstance(create_provider(config), DeterministicModelProvider)
        self.assertIsInstance(create_provider(), DeterministicModelProvider)

    def test_explicit_config_and_legacy_string_create_correct_instance(self) -> None:
        config = ProviderConfig(
            provider_id="deterministic",
            model_name="phase22-model-marker",
            endpoint="https://phase22.invalid/model",
        )
        provider = create_provider(config)
        self.assertIsInstance(provider, DeterministicModelProvider)
        self.assertIsInstance(create_provider("deterministic"), DeterministicModelProvider)
        request = {"messages": [{"role": "user", "content": "hello"}], "tools": []}
        self.assertEqual(provider.complete(**request), create_provider().complete(**request))

    def test_unknown_provider_fails_with_safe_structured_error(self) -> None:
        config = ProviderConfig(
            provider_id="phase22-unknown-provider",
            model_name="phase22-model-marker",
            endpoint="https://phase22.invalid/model",
        )
        with self.assertRaises(UnknownProviderError) as raised:
            create_provider(config)
        error = raised.exception.to_dict()
        self.assertEqual(error["code"], "unsupported_provider")
        self.assertIn("unsupported model provider", error["message"])
        self.assertNotIn(config.provider_id, str(raised.exception))
        self.assertNotIn(config.model_name, json.dumps(error))
        self.assertNotIn(config.endpoint, json.dumps(error))

    def test_legacy_name_keyword_remains_compatible_without_ambiguous_selection(self) -> None:
        self.assertIsInstance(create_provider(name="deterministic"), DeterministicModelProvider)
        with self.assertRaises(UnknownProviderError):
            create_provider(name="unknown")
        with self.assertRaises(ProviderConfigError):
            create_provider(ProviderConfig(), name="deterministic")

    def test_reserved_providers_have_no_adapter_or_fallback(self) -> None:
        self.assertEqual(
            set(RESERVED_PROVIDER_IDS),
            {"openai", "anthropic", "gemini", "local"},
        )
        for provider_id in RESERVED_PROVIDER_IDS:
            with self.subTest(provider_id=provider_id):
                with self.assertRaises(UnknownProviderError) as raised:
                    create_provider(ProviderConfig(provider_id=provider_id))
                self.assertEqual(raised.exception.to_dict()["code"], "unsupported_provider")

    def test_config_is_minimal_immutable_and_not_printed(self) -> None:
        config = ProviderConfig(model_name="model-marker", endpoint="endpoint-marker")
        self.assertEqual(
            {field.name for field in fields(config)},
            {"provider_id", "model_name", "endpoint", "api_key_env", "timeout_seconds"},
        )
        with self.assertRaises(FrozenInstanceError):
            config.provider_id = "local"
        self.assertNotIn("model-marker", repr(config))
        self.assertNotIn("endpoint-marker", repr(config))

    def test_invalid_config_fails_without_coercion_or_fallback(self) -> None:
        for values in (
            {"provider_id": ""},
            {"provider_id": "  "},
            {"provider_id": None},
            {"model_name": 123},
            {"endpoint": {}},
        ):
            with self.subTest(values=values):
                with self.assertRaises(ProviderConfigError) as raised:
                    ProviderConfig(**values)
                self.assertEqual(raised.exception.to_dict()["code"], "invalid_provider_config")
        with self.assertRaises(ProviderConfigError):
            create_provider({"provider_id": "deterministic"})

    def test_runtime_rejects_unknown_config_before_business_assembly(self) -> None:
        from desktop.python.runtime_bridge import build_workflow

        with patch("desktop.python.runtime_bridge.DatasetRegistry") as registry:
            with self.assertRaises(UnknownProviderError) as raised:
                build_workflow(
                    "thread_config_invalid",
                    None,
                    provider_config=ProviderConfig(provider_id="not-implemented"),
                )
            registry.assert_not_called()
            self.assertEqual(raised.exception.to_dict()["code"], "unsupported_provider")

    def test_runtime_config_preserves_analysis_and_stays_out_of_session_and_trace(self) -> None:
        from desktop.python.runtime_bridge import build_workflow, persist_run
        from session import SQLiteSessionStore

        config = ProviderConfig(
            model_name="phase22-model-marker",
            endpoint="https://phase22.invalid/model",
        )
        results = []
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = SQLiteSessionStore(root / "sessions.sqlite3")
            try:
                for index, selected in enumerate((None, config)):
                    thread_id = f"thread_config_{index}"
                    store.create_session(thread_id)
                    with patch("desktop.python.runtime_bridge.runtime_root", return_value=root):
                        workflow, runner = build_workflow(
                            thread_id,
                            store,
                            {"path": str(ROOT / "tests" / "fixtures" / "sales.csv"), "dataset_id": "ds_config_sales"},
                            provider_config=selected,
                        )
                    self.assertIsInstance(runner.loop.model, DeterministicModelProvider)
                    self.assertIs(workflow.nodes["analysis"].skill_runtime.runner.loop.model, runner.loop.model)
                    query = "计算销售额总和"
                    result = workflow.invoke({"query": query})
                    self.assertEqual(result["status"], "ok")
                    self.assertEqual(result["route"], "analysis")
                    trace = result["data"]["agent_state"]["execution_trace"]
                    self.assertEqual(trace[0]["tool_name"], "basic_stats")
                    self.assertEqual(trace[0]["data"]["value"], 1580)
                    persist_run(
                        store,
                        runner,
                        result,
                        thread_id=thread_id,
                        run_id=f"run_config_{index}",
                        query=query,
                        trace_id=result["data"]["observability"]["trace_id"],
                    )
                    serialized = json.dumps(
                        [result, store.get_messages(thread_id), store.get_events(thread_id)],
                        ensure_ascii=False,
                    )
                    for marker in (config.model_name, config.endpoint, "provider_id", "model_name", "endpoint", "provider_config"):
                        self.assertNotIn(marker, serialized)
                    results.append(
                        (result["response"], trace[0]["call_id"], trace[0]["arguments"], trace[0]["data"])
                    )
                self.assertEqual(results[0], results[1])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
