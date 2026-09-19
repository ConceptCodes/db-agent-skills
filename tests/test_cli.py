import argparse
import unittest

from langchain_core.messages import AIMessage

from db_agent_skills.cli import _positive_integer, response_text


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


if __name__ == "__main__":
    unittest.main()
