from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal

from langchain.agents.middleware import (
    AgentMiddleware,
    AgentState,
    ModelCallLimitMiddleware,
    PIIMiddleware,
    TracePolicy,
    ToolCallLimitMiddleware,
    hook_config,
    omit_payload,
)
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import Runnable
from langgraph.runtime import Runtime
from pydantic import BaseModel, ConfigDict, Field

from db_agent_skills.constants import (
    MAX_MODEL_CALLS_PER_RUN,
    MAX_TOOL_CALLS_PER_RUN,
)
from db_agent_skills.prompts import SCOPE_CLASSIFIER_PROMPT


logger = logging.getLogger(__name__)


MAX_SCOPE_CONTEXT_MESSAGES = 6
MAX_SCOPE_MESSAGE_CHARACTERS = 2_000

OUT_OF_SCOPE_RESPONSE = (
    "I can only help with read-only research and analysis of the selected "
    "database. Ask about its schema, data, metrics, relationships, data quality, "
    "or the SQL used to analyze it."
)

_CREDENTIAL_PATTERN = (
    r"(?i)(?:\bsk-(?:or-v1-)?[a-z0-9_-]{20,}\b|"
    r"\b(?:api[_-]?key|authorization|bearer|password|secret|token)"
    r"\s*[:=]\s*\S{12,})"
)
_PAYMENT_CARD_PATTERN = re.compile(
    r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?(\d{4})\b"
)


class ScopeDecision(BaseModel):
    """Structured result produced by the scope classifier."""

    model_config = ConfigDict(extra="forbid")

    decision: Literal["allow", "reject"] = Field(
        description="Allow only requests covered by the database research policy."
    )


class ScopeGuardrailMiddleware(AgentMiddleware):
    """Reject requests outside read-only database research before agent work."""

    trace_policy = TracePolicy(process_inputs=omit_payload)

    def __init__(self, classifier: Runnable[Any, ScopeDecision]) -> None:
        super().__init__()
        self._classifier = classifier

    @hook_config(can_jump_to=["end"])
    def before_agent(
        self,
        state: AgentState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        del runtime
        classifier_messages = _scope_classifier_messages(state.get("messages", []))
        if classifier_messages is None:
            return None

        try:
            decision = ScopeDecision.model_validate(
                self._classifier.invoke(classifier_messages)
            )
        except Exception as error:  # noqa: BLE001 - fail closed at trust boundary
            logger.warning(
                "Scope classification failed: %s",
                type(error).__name__,
            )
            return _scope_rejection()

        return None if decision.decision == "allow" else _scope_rejection()

    @hook_config(can_jump_to=["end"])
    async def abefore_agent(
        self,
        state: AgentState,
        runtime: Runtime,
    ) -> dict[str, Any] | None:
        del runtime
        classifier_messages = _scope_classifier_messages(state.get("messages", []))
        if classifier_messages is None:
            return None

        try:
            decision = ScopeDecision.model_validate(
                await self._classifier.ainvoke(classifier_messages)
            )
        except Exception as error:  # noqa: BLE001 - fail closed at trust boundary
            logger.warning(
                "Scope classification failed: %s",
                type(error).__name__,
            )
            return _scope_rejection()

        return None if decision.decision == "allow" else _scope_rejection()


def _scope_classifier_messages(
    messages: list[Any],
) -> list[SystemMessage | HumanMessage] | None:
    conversation = []
    for message in messages:
        if not isinstance(message, (HumanMessage, AIMessage)):
            continue
        text = _sanitize_scope_text(message.text.strip())
        if not text:
            continue
        conversation.append(
            {
                "role": "user" if isinstance(message, HumanMessage) else "assistant",
                "content": text[:MAX_SCOPE_MESSAGE_CHARACTERS],
            }
        )

    if not conversation or conversation[-1]["role"] != "user":
        return None

    bounded_conversation = conversation[-MAX_SCOPE_CONTEXT_MESSAGES:]
    return [
        SystemMessage(content=SCOPE_CLASSIFIER_PROMPT),
        HumanMessage(
            content=(
                "Classify this conversation data. Return only the structured "
                "decision.\n<conversation_data>\n"
                f"{json.dumps(bounded_conversation, ensure_ascii=True)}\n"
                "</conversation_data>"
            )
        ),
    ]


def _sanitize_scope_text(text: str) -> str:
    sanitized = re.sub(_CREDENTIAL_PATTERN, "[REDACTED_CREDENTIAL]", text)
    return _PAYMENT_CARD_PATTERN.sub(
        lambda match: f"****-****-****-{match.group(1)}",
        sanitized,
    )


def _scope_rejection() -> dict[str, Any]:
    return {
        "messages": [AIMessage(content=OUT_OF_SCOPE_RESPONSE)],
        "jump_to": "end",
    }


def create_agent_guardrails(scope_model: BaseChatModel) -> list[AgentMiddleware]:
    """Create deterministic limits and sensitive-data protections."""
    return [
        ScopeGuardrailMiddleware(
            scope_model.with_structured_output(ScopeDecision)
        ),
        ModelCallLimitMiddleware(
            run_limit=MAX_MODEL_CALLS_PER_RUN,
            exit_behavior="end",
        ),
        ToolCallLimitMiddleware(
            run_limit=MAX_TOOL_CALLS_PER_RUN,
            exit_behavior="end",
        ),
        PIIMiddleware(
            "credential_input",
            detector=_CREDENTIAL_PATTERN,
            strategy="block",
            apply_to_input=True,
        ),
        PIIMiddleware(
            "credential_data",
            detector=_CREDENTIAL_PATTERN,
            strategy="redact",
            apply_to_input=False,
            apply_to_output=True,
            apply_to_tool_results=True,
        ),
        PIIMiddleware(
            "credit_card",
            strategy="mask",
            apply_to_input=True,
            apply_to_output=True,
            apply_to_tool_results=True,
        ),
    ]
