from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent import AgentLoop, ConversationRunner
from datasets import DatasetRegistry
from providers import (
    DeterministicModelProvider,
    ModelProvider,
    UnknownProviderError,
    create_provider,
)
from skill_runtime import SkillRegistry, SkillRuntime
from skill_runtime.tool_view import build_skill_tool_view
from tools import build_default_registry


def tool_schema(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": name,
            "parameters": {"type": "object", "properties": {}},
        },
    }


def dataset_message(question: str, *, complete: bool = True) -> dict:
    dataset = {
        "columns": [
            {"name": "地区", "type": "text"},
            {"name": "日期", "type": "date"},
            {"name": "销售额", "type": "number"},
        ]
    }
    if complete:
        dataset["datasetId"] = "ds_sales"
    return {
        "role": "user",
        "content": question,
        "dataset_context": {"datasets": [dataset]},
    }


class ProviderContractTests(unittest.TestCase):
    def test_factory_supports_only_deterministic(self) -> None:
        provider = create_provider()
        self.assertIsInstance(provider, DeterministicModelProvider)
        self.assertIsInstance(provider, ModelProvider)
        with self.assertRaisesRegex(UnknownProviderError, "unsupported model provider"):
            create_provider("openai")

    def test_final_answer_matches_desktop_bridge_behavior(self) -> None:
        provider = DeterministicModelProvider()
        self.assertEqual(
            provider.complete(messages=[{"role": "user", "content": "hello"}], tools=[]),
            {"type": "final_answer", "content": "Desktop Runtime 已完成本次请求。"},
        )
        observation = json.dumps(
            {"ok": True, "data": {"value": 1580}, "error": None},
            ensure_ascii=False,
        )
        self.assertEqual(
            provider.complete(
                messages=[
                    dataset_message("计算销售额总和"),
                    {
                        "role": "tool",
                        "name": "basic_stats",
                        "tool_call_id": "call-1",
                        "content": observation,
                    },
                ],
                tools=[tool_schema("basic_stats")],
            ),
            {"type": "final_answer", "content": '分析完成：{"value":1580}'},
        )

    def test_needs_user_input_matches_desktop_bridge_behavior(self) -> None:
        provider = DeterministicModelProvider()
        self.assertEqual(
            provider.complete(
                messages=[dataset_message("分析销售额", complete=False)],
                tools=[tool_schema("basic_stats")],
            ),
            {"type": "needs_user_input", "content": "数据集摘要不完整，请重新选择文件。"},
        )

    def test_tool_call_and_tools_schema_match_desktop_bridge_behavior(self) -> None:
        provider = DeterministicModelProvider()
        self.assertEqual(
            provider.complete(
                messages=[dataset_message("按地区统计销售额")],
                tools=[tool_schema("group_compare"), tool_schema("basic_stats")],
            ),
            {
                "type": "tool_call",
                "id": "bridge_analysis_1",
                "name": "group_compare",
                "arguments": {
                    "datasetId": "ds_sales",
                    "groupBy": "地区",
                    "metric": "销售额",
                    "operation": "sum",
                },
            },
        )
        self.assertEqual(
            provider.complete(
                messages=[dataset_message("计算销售额总和")],
                tools=[tool_schema("basic_stats")],
            ),
            {
                "type": "tool_call",
                "id": "bridge_analysis_1",
                "name": "basic_stats",
                "arguments": {
                    "datasetId": "ds_sales",
                    "metric": "销售额",
                    "operation": "sum",
                },
            },
        )

    def test_skill_loop_reuses_the_same_provider_instance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            datasets = DatasetRegistry(Path(directory) / "datasets")
            provider = create_provider()
            runner = ConversationRunner(
                AgentLoop(provider, build_default_registry()),
                dataset_registry=datasets,
                conversation_id="provider-skill-test",
            )
            runtime = SkillRuntime(runner, SkillRegistry())
            definition = runtime.registry.load("data-diagnosis")
            tool_view = build_skill_tool_view(
                runner.loop.registry, definition.allowed_tools
            )
            skill_loop = runtime._build_loop(definition, tool_view)
            self.assertIs(skill_loop.model, provider)

    def test_desktop_composition_uses_deterministic_provider_by_default(self) -> None:
        from desktop.python.runtime_bridge import build_workflow
        from session import SQLiteSessionStore

        with tempfile.TemporaryDirectory() as directory:
            store = SQLiteSessionStore(Path(directory) / "sessions.sqlite3")
            try:
                store.create_session("thread_provider_test")
                workflow, _ = build_workflow("thread_provider_test", store)
                analysis = workflow.nodes["analysis"]
                self.assertIsInstance(
                    analysis.runner.loop.model, DeterministicModelProvider
                )
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
