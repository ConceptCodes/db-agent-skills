import argparse
import io
import unittest
from collections.abc import Iterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from rich.console import Console

from db_agent_skills.cli import (
    DEFAULT_RECURSION_LIMIT,
    _positive_integer,
    _safe_preview,
    build_parser,
    response_text,
    stream_agent_response,
)
from db_agent_skills.constants import (
    MAX_MODEL_CALLS_PER_RUN,
    MAX_TOOL_CALLS_PER_RUN,
)


class FakeStreamingAgent:
    def stream(
        self,
        _invocation: dict[str, Any],
        *,
        config: dict[str, Any],
        stream_mode: list[str],
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        assert config["configurable"]["thread_id"] == "test-thread"
        assert stream_mode == ["updates", "values"]

        user_message = HumanMessage(content="Count the orders")
        tool_call = {
            "name": "sql_db_query",
            "args": {"query": "SELECT COUNT(*) FROM Orders"},
            "id": "call-1",
            "type": "tool_call",
        }
        call_message = AIMessage(content="", tool_calls=[tool_call])
        result_message = ToolMessage(
            content="[(830,)]",
            name="sql_db_query",
            tool_call_id="call-1",
        )
        final_message = AIMessage(content="There are **830 orders**.")

        yield "values", {"messages": [user_message]}
        yield "updates", {"model": {"messages": [call_message]}}
        yield "values", {"messages": [user_message, call_message]}
        yield "updates", {"tools": {"messages": [result_message]}}
        yield "values", {
            "messages": [user_message, call_message, result_message]
        }
        yield "updates", {"model": {"messages": [final_message]}}
        yield "values", {
            "messages": [
                user_message,
                call_message,
                result_message,
                final_message,
            ]
        }


class FakeLimitStoppedAgent:
    def __init__(self, node_name: str, message: str) -> None:
        self.node_name = node_name
        self.message = message

    def stream(
        self,
        _invocation: dict[str, Any],
        *,
        config: dict[str, Any],
        stream_mode: list[str],
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        del config, stream_mode
        user_message = HumanMessage(content="Research the database")
        yield "values", {"messages": [user_message]}
        yield "updates", {
            self.node_name: {
                "messages": [AIMessage(content=self.message)],
                "jump_to": "end",
            }
        }


class CliTests(unittest.TestCase):
    def test_extracts_text_from_structured_message_content(self) -> None:
        message = AIMessage(
            content=[
                {"type": "text", "text": "# Result\n\n**42 rows**"},
                {"type": "reasoning", "reasoning": "internal"},
            ]
        )

        self.assertEqual(response_text([message]), "# Result\n\n**42 rows**")

    def test_recursion_limit_must_be_positive(self) -> None:
        self.assertEqual(_positive_integer("5"), 5)
        with self.assertRaisesRegex(argparse.ArgumentTypeError, "at least 1"):
            _positive_integer("0")

    def test_default_recursion_limit_allows_skill_workflows(self) -> None:
        args = build_parser().parse_args([])

        self.assertEqual(args.recursion_limit, DEFAULT_RECURSION_LIMIT)
        self.assertEqual(args.recursion_limit, 50)

    def test_streams_tool_activity_and_returns_final_response(self) -> None:
        output = io.StringIO()
        console = Console(file=output, color_system=None, width=100)

        answer = stream_agent_response(
            FakeStreamingAgent(),
            {"messages": [{"role": "user", "content": "Count the orders"}]},
            {
                "configurable": {"thread_id": "test-thread"},
                "recursion_limit": 25,
            },
            console=console,
        )

        trace = output.getvalue()
        self.assertIn("Tool call", trace)
        self.assertIn("sql_db_query", trace)
        self.assertIn("SELECT COUNT(*) FROM Orders", trace)
        self.assertIn("[(830,)]", trace)
        self.assertIn("Response ready", trace)
        self.assertEqual(answer, "There are **830 orders**.")

    def test_surfaces_model_call_limit_terminal_update(self) -> None:
        self._assert_limit_stop_is_visible(
            "ModelCallLimitMiddleware.before_model",
            "Model call limits exceeded: run limit (16/16)",
            f"safety limit of {MAX_MODEL_CALLS_PER_RUN} model calls",
        )

    def test_surfaces_tool_call_limit_terminal_update(self) -> None:
        self._assert_limit_stop_is_visible(
            "ToolCallLimitMiddleware.after_model",
            "Tool call limit reached: run limit exceeded (25/24 calls).",
            f"safety limit of {MAX_TOOL_CALLS_PER_RUN} tool calls",
        )

    def test_trace_preview_redacts_secrets_and_has_a_size_limit(self) -> None:
        preview = _safe_preview(
            {
                "authorization": "Bearer should-not-appear",
                "card": "5105-1051-0510-5100",
                "result": "x" * 100,
            },
            limit=120,
        )

        self.assertNotIn("should-not-appear", preview)
        self.assertNotIn("5105-1051-0510-5100", preview)
        self.assertIn("****-****-****-5100", preview)
        self.assertIn("[REDACTED]", preview)
        self.assertIn("characters omitted", preview)

    def _assert_limit_stop_is_visible(
        self,
        node_name: str,
        internal_message: str,
        expected_message: str,
    ) -> None:
        output = io.StringIO()
        console = Console(file=output, color_system=None, width=100)

        answer = stream_agent_response(
            FakeLimitStoppedAgent(node_name, internal_message),
            {"messages": [{"role": "user", "content": "Research the database"}]},
            {"configurable": {"thread_id": "test-thread"}},
            console=console,
        )

        self.assertIn("Request stopped by a guardrail", output.getvalue())
        self.assertIn(expected_message, answer)
        self.assertNotEqual(answer, internal_message)


if __name__ == "__main__":
    unittest.main()
