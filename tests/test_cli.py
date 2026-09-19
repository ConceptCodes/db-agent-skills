import argparse
import io
import unittest
from collections.abc import Iterator
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from rich.console import Console

from db_agent_skills.cli import (
    _positive_integer,
    _safe_preview,
    response_text,
    stream_agent_response,
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

    def test_trace_preview_redacts_secrets_and_has_a_size_limit(self) -> None:
        preview = _safe_preview(
            {"authorization": "Bearer should-not-appear", "result": "x" * 100},
            limit=60,
        )

        self.assertNotIn("should-not-appear", preview)
        self.assertIn("[REDACTED]", preview)
        self.assertIn("characters omitted", preview)


if __name__ == "__main__":
    unittest.main()
