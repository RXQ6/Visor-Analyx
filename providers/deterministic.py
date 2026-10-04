"""Deterministic model provider used by the Desktop composition root."""

from __future__ import annotations

import json
from typing import Any


class DeterministicModelProvider:
    """Preserve the original Desktop BridgeModel decision behavior exactly."""

    def complete(
        self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]:
        available = {item.get("function", {}).get("name") for item in tools}
        user_index = next(
            (
                index
                for index in range(len(messages) - 1, -1, -1)
                if messages[index].get("role") == "user"
            ),
            -1,
        )
        user = messages[user_index] if user_index >= 0 else {}
        question = str(user.get("content", ""))
        dataset_context = user.get("dataset_context")
        datasets = (
            dataset_context.get("datasets", [])
            if isinstance(dataset_context, dict)
            else []
        )
        dataset = datasets[-1] if datasets else None
        tool_message = next(
            (
                item
                for item in reversed(messages[user_index + 1 :])
                if item.get("role") == "tool"
            ),
            None,
        )
        wants_chart = any(
            term in question.lower() for term in ("图", "chart", "visual")
        )

        if isinstance(tool_message, dict):
            try:
                observation = json.loads(str(tool_message.get("content", "{}")))
            except json.JSONDecodeError:
                return {
                    "type": "final_answer",
                    "content": "工具结果无法解析，分析未完成。",
                }
            if not observation.get("ok"):
                error = observation.get("error") or {}
                return {
                    "type": "final_answer",
                    "content": f"分析工具失败：{error.get('message', error.get('code', 'unknown error'))}",
                }
            tool_name = str(tool_message.get("name", ""))
            if (
                wants_chart
                and tool_name != "generate_chart"
                and "generate_chart" in available
            ):
                chart_type = (
                    "line"
                    if tool_name == "trend_analysis"
                    else "scatter"
                    if tool_name == "scatter_data"
                    else "bar"
                )
                return {
                    "type": "tool_call",
                    "id": f"bridge_chart_{len(messages)}",
                    "name": "generate_chart",
                    "arguments": {
                        "sourceCallId": str(tool_message.get("tool_call_id")),
                        "chartType": chart_type,
                    },
                }
            if tool_name == "generate_chart":
                return {"type": "final_answer", "content": "分析完成，图表已生成。"}
            data = observation.get("data")
            summary = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            return {"type": "final_answer", "content": "分析完成：" + summary}

        if any(
            term in question.lower()
            for term in ("外部写", "mcp write", "external write")
        ) and "mcp_mock__echo" in available:
            return {
                "type": "tool_call",
                "id": f"bridge_write_{len(messages)}",
                "name": "mcp_mock__echo",
                "arguments": {"text": question},
            }
        if not isinstance(dataset, dict):
            return {
                "type": "final_answer",
                "content": "Desktop Runtime 已完成本次请求。",
            }
        dataset_id = dataset.get("datasetId")
        columns = dataset.get("columns", [])
        if not isinstance(dataset_id, str) or not isinstance(columns, list):
            return {
                "type": "needs_user_input",
                "content": "数据集摘要不完整，请重新选择文件。",
            }
        named = [
            item
            for item in columns
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ]
        number_columns = [
            item["name"] for item in named if item.get("type") == "number"
        ]
        date_columns = [
            item["name"] for item in named if item.get("type") == "date"
        ]
        text_columns = [
            item["name"] for item in named if item.get("type") == "text"
        ]
        metric = next(
            (name for name in number_columns if name in question),
            number_columns[0] if number_columns else None,
        )
        group = next(
            (name for name in text_columns if name in question),
            text_columns[0] if text_columns else None,
        )
        date_field = next(
            (name for name in date_columns if name in question),
            date_columns[0] if date_columns else None,
        )
        operation = (
            "average"
            if any(term in question for term in ("平均", "均值"))
            else "maximum"
            if "最大" in question
            else "minimum"
            if "最小" in question
            else "count"
            if any(term in question for term in ("计数", "数量"))
            else "sum"
        )
        call: dict[str, Any] | None = None
        if metric and date_field and any(
            term in question for term in ("趋势", "变化", "按日期", "折线")
        ):
            call = {
                "name": "trend_analysis",
                "arguments": {
                    "datasetId": dataset_id,
                    "dateField": date_field,
                    "metric": metric,
                    "operation": operation,
                },
            }
        elif metric and group and any(
            term in question for term in ("按", "分组", "对比", "柱状")
        ):
            call = {
                "name": "group_compare",
                "arguments": {
                    "datasetId": dataset_id,
                    "groupBy": group,
                    "metric": metric,
                    "operation": operation,
                },
            }
        elif metric:
            call = {
                "name": "basic_stats",
                "arguments": {
                    "datasetId": dataset_id,
                    "metric": metric,
                    "operation": operation,
                },
            }
        elif "inspect_data" in available:
            call = {
                "name": "inspect_data",
                "arguments": {"datasetId": dataset_id},
            }
        if call is None or call["name"] not in available:
            return {
                "type": "needs_user_input",
                "content": "请明确要分析的字段和统计方式。",
            }
        return {
            "type": "tool_call",
            "id": f"bridge_analysis_{len(messages)}",
            **call,
        }
