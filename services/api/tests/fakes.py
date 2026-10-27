"""Test doubles for the agent: a scripted Anthropic client and canned tool results."""

import json
from collections.abc import Callable
from typing import Any

from anthropic.types import Message

from app.agent.tools import ToolContext, ToolResult


def message(
    content: list[dict[str, Any]],
    stop_reason: str = "end_turn",
    tokens: tuple[int, int] = (100, 20),
) -> Message:
    return Message.model_validate(
        {
            "id": "msg_test",
            "type": "message",
            "role": "assistant",
            "model": "test",
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": tokens[0], "output_tokens": tokens[1]},
        }
    )


def guard_reply(category: str) -> Message:
    return message([{"type": "text", "text": json.dumps({"category": category, "reason": "t"})}])


def tool_use(name: str, arguments: dict[str, Any], use_id: str = "tu_1") -> Message:
    return message(
        [{"type": "tool_use", "id": use_id, "name": name, "input": arguments}],
        stop_reason="tool_use",
    )


def final_answer(**fields: Any) -> Message:
    answer = {
        "text": "Answer.",
        "assumptions": [],
        "table_result_id": "",
        "table_rows": 0,
        "chart": {"type": "none", "x": "", "y": ""},
        "citations": [],
    } | fields
    return message(
        [{"type": "tool_use", "id": "tu_final", "name": "final_answer", "input": answer}],
        stop_reason="tool_use",
    )


class _Messages:
    def __init__(self, script: Callable[[dict[str, Any]], Message]) -> None:
        self.calls: list[dict[str, Any]] = []
        self._script = script

    def create(self, **kwargs: Any) -> Message:
        self.calls.append(kwargs)
        return self._script(kwargs)


class FakeClient:
    """Answers `messages.create` by model: the guard model gets `guard`, the main model `main`."""

    def __init__(self, guard: Message, main: list[Message] | Callable[[], Message]) -> None:
        replies = iter(main) if isinstance(main, list) else None

        def script(kwargs: dict[str, Any]) -> Message:
            if kwargs["model"] == "claude-haiku-5-5":
                return guard
            if replies is not None:
                return next(replies)
            assert callable(main)
            return main()

        self.messages = _Messages(script)

    def main_calls(self) -> list[dict[str, Any]]:
        return [c for c in self.messages.calls if c["model"] == "claude-sonnet-5-5"]


def canned_tool(**fields: Any) -> Callable[[ToolContext, str, dict[str, Any]], ToolResult]:
    """A call_tool replacement that records a fixed result on the context."""

    def call(ctx: ToolContext, name: str, arguments: dict[str, Any]) -> ToolResult:
        return ctx.new_result(name, fields.get("status", "ok"), **{
            k: v for k, v in fields.items() if k != "status"
        })  # fmt: skip

    return call
