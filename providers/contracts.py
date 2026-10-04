"""Shared structural contract for model providers.

The runtime deliberately keeps the existing ``complete(messages, tools)``
shape.  Providers translate their native response into one of these decisions
before returning control to AgentLoop.
"""

from __future__ import annotations

from typing import Any, Literal, Protocol, TypedDict, runtime_checkable


class ModelMessage(TypedDict, total=False):
    role: str
    content: Any
    name: str
    tool_call_id: str
    tool_calls: list[dict[str, Any]]
    dataset_context: dict[str, Any]
    schema: dict[str, Any] | list[Any] | None


class ToolFunctionSchema(TypedDict, total=False):
    name: str
    description: str
    parameters: dict[str, Any]


class ToolSchema(TypedDict, total=False):
    type: Literal["function"]
    function: ToolFunctionSchema


class FinalAnswerDecision(TypedDict):
    type: Literal["final_answer"]
    content: str


class NeedsUserInputDecision(TypedDict):
    type: Literal["needs_user_input"]
    content: str


class ToolCallDecision(TypedDict):
    type: Literal["tool_call"]
    id: str
    name: str
    arguments: dict[str, Any]


ModelDecision = FinalAnswerDecision | NeedsUserInputDecision | ToolCallDecision | dict[str, Any]


@runtime_checkable
class ModelProvider(Protocol):
    """The synchronous model boundary currently consumed by AgentLoop."""

    def complete(
        self, *, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> dict[str, Any]: ...
