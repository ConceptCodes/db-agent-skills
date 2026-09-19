import unittest
from typing import Any

from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    PIIDetectionError,
    PIIMiddleware,
    ToolCallLimitMiddleware,
)
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from db_agent_skills.constants import (
    MAX_MODEL_CALLS_PER_RUN,
    MAX_TOOL_CALLS_PER_RUN,
)
from db_agent_skills.guardrails import (
    OUT_OF_SCOPE_RESPONSE,
    ScopeDecision,
    ScopeGuardrailMiddleware,
    create_agent_guardrails,
)


class FakeScopeClassifier:
    def __init__(
        self,
        decision: str = "allow",
        error: Exception | None = None,
    ) -> None:
        self.decision = decision
        self.error = error
        self.calls: list[list[BaseMessage]] = []

    def invoke(self, messages: list[BaseMessage]) -> ScopeDecision:
        self.calls.append(messages)
        if self.error is not None:
            raise self.error
        return ScopeDecision(decision=self.decision)

    async def ainvoke(self, messages: list[BaseMessage]) -> ScopeDecision:
        return self.invoke(messages)


class FakeScopeModel:
    def __init__(self, classifier: FakeScopeClassifier) -> None:
        self.classifier = classifier

    def with_structured_output(self, schema: type[ScopeDecision]) -> FakeScopeClassifier:
        assert schema is ScopeDecision
        return self.classifier


class AgentGuardrailTests(unittest.TestCase):
    def setUp(self) -> None:
        self.classifier = FakeScopeClassifier()
        self.guardrails = create_agent_guardrails(  # type: ignore[arg-type]
            FakeScopeModel(self.classifier)
        )

    def test_rejects_out_of_scope_requests_before_agent_work(self) -> None:
        guardrail = ScopeGuardrailMiddleware(
            FakeScopeClassifier(decision="reject")  # type: ignore[arg-type]
        )

        update = guardrail.before_agent(
            {"messages": [HumanMessage(content="Write me a poem")]},
            runtime=None,
        )

        self.assertIsNotNone(update)
        assert update is not None
        self.assertEqual(update["jump_to"], "end")
        self.assertEqual(update["messages"][-1].content, OUT_OF_SCOPE_RESPONSE)

    def test_allows_database_research_and_contextual_follow_ups(self) -> None:
        guardrail = self._scope_guardrail()

        update = guardrail.before_agent(
            {
                "messages": [
                    HumanMessage(content="Show the top customers by revenue"),
                    AIMessage(content="Here are the results for all years."),
                    HumanMessage(content="What about 1997?"),
                ]
            },
            runtime=None,
        )

        self.assertIsNone(update)
        classifier_input = self.classifier.calls[-1][-1].text
        self.assertIn("top customers by revenue", classifier_input)
        self.assertIn("What about 1997?", classifier_input)

    def test_redacts_sensitive_values_before_scope_classification(self) -> None:
        guardrail = self._scope_guardrail()

        guardrail.before_agent(
            {
                "messages": [
                    HumanMessage(
                        content=(
                            "Query token: abcdefghijklmnopqrstuvwxyz and card "
                            "5105-1051-0510-5100"
                        )
                    )
                ]
            },
            runtime=None,
        )

        classifier_input = self.classifier.calls[-1][-1].text
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", classifier_input)
        self.assertNotIn("5105-1051-0510-5100", classifier_input)
        self.assertIn("[REDACTED_CREDENTIAL]", classifier_input)
        self.assertIn("****-****-****-5100", classifier_input)

    def test_scope_classifier_fails_closed(self) -> None:
        guardrail = ScopeGuardrailMiddleware(  # type: ignore[arg-type]
            FakeScopeClassifier(error=RuntimeError("provider unavailable"))
        )

        with self.assertLogs("db_agent_skills.guardrails", level="WARNING"):
            update = guardrail.before_agent(
                {"messages": [HumanMessage(content="Count the orders")]},
                runtime=None,
            )

        self.assertIsNotNone(update)
        assert update is not None
        self.assertEqual(update["jump_to"], "end")

    def test_limits_model_and_tool_calls_per_run(self) -> None:
        model_limit = next(
            guardrail
            for guardrail in self.guardrails
            if isinstance(guardrail, ModelCallLimitMiddleware)
        )
        tool_limit = next(
            guardrail
            for guardrail in self.guardrails
            if isinstance(guardrail, ToolCallLimitMiddleware)
        )

        self.assertEqual(model_limit.run_limit, MAX_MODEL_CALLS_PER_RUN)
        self.assertEqual(model_limit.exit_behavior, "end")
        self.assertEqual(tool_limit.run_limit, MAX_TOOL_CALLS_PER_RUN)
        self.assertEqual(tool_limit.exit_behavior, "end")

    def test_blocks_credentials_in_user_input(self) -> None:
        guardrail = self._pii_guardrail("credential_input")

        with self.assertRaises(PIIDetectionError):
            guardrail.before_model(
                {
                    "messages": [
                        HumanMessage(
                            content="OPENROUTER_API_KEY=sk-or-v1-1234567890abcdefghij"
                        )
                    ]
                },
                runtime=None,
            )

    def test_redacts_credentials_from_model_output(self) -> None:
        guardrail = self._pii_guardrail("credential_data")
        update = guardrail.after_model(
            {
                "messages": [
                    AIMessage(content="token: abcdefghijklmnopqrstuvwxyz")
                ]
            },
            runtime=None,
        )

        self.assertIsNotNone(update)
        assert update is not None
        self.assertEqual(
            update["messages"][-1].content,
            "[REDACTED_CREDENTIAL_DATA]",
        )

    def test_masks_credit_cards_in_model_output(self) -> None:
        guardrail = self._pii_guardrail("credit_card")
        update = guardrail.after_model(
            {"messages": [AIMessage(content="Card: 5105-1051-0510-5100")]},
            runtime=None,
        )

        self.assertIsNotNone(update)
        assert update is not None
        self.assertEqual(
            update["messages"][-1].content,
            "Card: ****-****-****-5100",
        )

    def _pii_guardrail(self, pii_type: str) -> PIIMiddleware:
        return next(
            guardrail
            for guardrail in self.guardrails
            if isinstance(guardrail, PIIMiddleware)
            and guardrail.pii_type == pii_type
        )

    def _scope_guardrail(self) -> ScopeGuardrailMiddleware:
        return next(
            guardrail
            for guardrail in self.guardrails
            if isinstance(guardrail, ScopeGuardrailMiddleware)
        )


if __name__ == "__main__":
    unittest.main()
