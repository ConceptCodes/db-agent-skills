from __future__ import annotations

import argparse
import json
import re
import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from langchain.agents.middleware import PIIDetectionError
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langgraph.errors import GraphRecursionError
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text
from rich.theme import Theme

from db_agent_skills.config import get_settings
from db_agent_skills.constants import (
    MAX_MODEL_CALLS_PER_RUN,
    MAX_TOOL_CALLS_PER_RUN,
)


MAX_INPUT_CHARACTERS = 8_000
MAX_TRACE_CHARACTERS = 2_000
DEFAULT_RECURSION_LIMIT = 50

_CONTROL_CHARACTERS = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")
_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(
        r"(?i)\b(bearer|api[_-]?key|authorization|password|secret|token)"
        r"(\s*[:=]\s*)\S+"
    ),
)
_PAYMENT_CARD_PATTERN = re.compile(
    r"\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?(\d{4})\b"
)
_SENSITIVE_FIELD_NAMES = frozenset(
    {"api_key", "authorization", "password", "secret", "token"}
)

THEME = Theme(
    {
        "accent": "bold bright_cyan",
        "assistant": "bold bright_green",
        "activity": "bold bright_blue",
        "tool": "bold bright_magenta",
        "success": "bold green",
        "muted": "dim white",
        "warning": "bold yellow",
        "error": "bold bright_red",
    }
)

COMMANDS = {
    "/help": "Show available commands",
    "/new": "Start a new in-memory conversation",
    "/clear": "Clear the terminal",
    "/thread": "Show the current thread ID",
    "/exit": "Exit the chat",
}

def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="db-agent-skills",
        description="Chat with the read-only SQLite research agent.",
    )
    parser.add_argument(
        "--thread-id",
        help="Conversation thread ID. A random ID is used when omitted.",
    )
    parser.add_argument(
        "--recursion-limit",
        type=_positive_integer,
        default=DEFAULT_RECURSION_LIMIT,
        help=f"Maximum agent graph steps per message (default: {DEFAULT_RECURSION_LIMIT}).",
    )
    return parser


def response_text(messages: Sequence[BaseMessage]) -> str:
    """Return the final model message as displayable text."""
    if not messages:
        return "The agent returned no messages."

    final_message = messages[-1]
    if not isinstance(final_message, AIMessage) or final_message.tool_calls:
        return "The agent stopped before producing a final response."

    text = final_message.text.strip()
    return text or "The agent returned an empty response."


def _latest_ai_response(messages: Sequence[BaseMessage]) -> str | None:
    """Return the latest complete AI response from one stream update."""
    for message in reversed(messages):
        if not isinstance(message, AIMessage) or message.tool_calls:
            continue
        text = message.text.strip()
        if text:
            return text
    return None


def _guardrail_stop_response(node_name: str, fallback: str) -> str:
    """Translate internal call-limit stops into actionable user messages."""
    if node_name.startswith("ModelCallLimitMiddleware."):
        return (
            "I stopped this request after it reached the safety limit of "
            f"{MAX_MODEL_CALLS_PER_RUN} model calls without finishing. "
            "Try a narrower question or start a new conversation."
        )
    if node_name.startswith("ToolCallLimitMiddleware."):
        return (
            "I stopped this request after it reached the safety limit of "
            f"{MAX_TOOL_CALLS_PER_RUN} tool calls without finishing. "
            "Review the activity trace for repeated calls, then try a narrower "
            "question."
        )
    return fallback


def _safe_preview(value: Any, *, limit: int = MAX_TRACE_CHARACTERS) -> str:
    """Format an untrusted event value for bounded terminal display."""
    def redact_fields(item: Any) -> Any:
        if isinstance(item, Mapping):
            return {
                key: (
                    "[REDACTED]"
                    if str(key).lower() in _SENSITIVE_FIELD_NAMES
                    else redact_fields(nested_value)
                )
                for key, nested_value in item.items()
            }
        if isinstance(item, Sequence) and not isinstance(item, (str, bytes)):
            return [redact_fields(nested_value) for nested_value in item]
        return item

    redacted_value = redact_fields(value)
    if isinstance(redacted_value, str):
        preview = redacted_value
    else:
        try:
            preview = json.dumps(
                redacted_value,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        except (TypeError, ValueError):
            preview = str(redacted_value)

    preview = _CONTROL_CHARACTERS.sub("�", preview)
    for pattern in _SECRET_PATTERNS:
        preview = pattern.sub(
            lambda match: (
                f"{match.group(1)}{match.group(2)}[REDACTED]"
                if match.lastindex == 2
                else "[REDACTED]"
            ),
            preview,
        )
    preview = _PAYMENT_CARD_PATTERN.sub(
        lambda match: f"****-****-****-{match.group(1)}",
        preview,
    )

    if len(preview) <= limit:
        return preview

    omitted = len(preview) - limit
    return f"{preview[:limit]}\n… {omitted:,} characters omitted"


def _update_messages(update: Any) -> list[BaseMessage]:
    if not isinstance(update, Mapping):
        return []

    messages = update.get("messages", [])
    if isinstance(messages, BaseMessage):
        return [messages]
    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
        return []
    return [message for message in messages if isinstance(message, BaseMessage)]


def _print_payload(console: Console, value: Any, *, border_style: str) -> None:
    preview = _safe_preview(value)
    if not preview:
        return
    console.print(
        Panel(
            Text(preview),
            border_style=border_style,
            padding=(0, 1),
            expand=False,
        )
    )


def _print_activity_update(console: Console, update: Any) -> None:
    """Render observable graph updates without exposing model reasoning."""
    if not isinstance(update, Mapping):
        return

    for node_name, node_update in update.items():
        messages = _update_messages(node_update)
        rendered_message = False
        stopped = (
            isinstance(node_update, Mapping)
            and node_update.get("jump_to") == "end"
        )

        for message in messages:
            if isinstance(message, AIMessage):
                if message.tool_calls:
                    for tool_call in message.tool_calls:
                        tool_name = str(tool_call.get("name") or "unknown_tool")
                        label = Text("  → Tool call  ", style="tool")
                        label.append(tool_name, style="bold white")
                        console.print(label)
                        _print_payload(
                            console,
                            tool_call.get("args", {}),
                            border_style="magenta",
                        )
                else:
                    if stopped:
                        console.print(
                            "  [warning]⚠ Request stopped by a guardrail[/warning]"
                        )
                    else:
                        console.print("  [success]✓ Response ready[/success]")
                rendered_message = True
                continue

            if isinstance(message, ToolMessage):
                tool_name = message.name or message.tool_call_id or "unknown_tool"
                failed = getattr(message, "status", "success") == "error"
                style = "error" if failed else "success"
                marker = "✗" if failed else "←"
                label = Text(f"  {marker} Tool result  ", style=style)
                label.append(str(tool_name), style="bold white")
                console.print(label)
                _print_payload(
                    console,
                    message.text or message.content,
                    border_style="red" if failed else "green",
                )
                rendered_message = True

        if not rendered_message:
            label = Text("  • Step  ", style="activity")
            label.append(str(node_name), style="white")
            console.print(label)


def stream_agent_response(
    chat_agent: Any,
    invocation: Mapping[str, Any],
    config: Mapping[str, Any],
    *,
    console: Console,
) -> str:
    """Stream agent activity and return the final response text."""
    final_state: Mapping[str, Any] = {}
    streamed_response: str | None = None
    guardrail_response: str | None = None
    console.rule("[activity]Activity[/activity]", style="bright_blue")

    try:
        with console.status(
            "[accent]Waiting for the agent…[/accent]",
            spinner="dots",
            spinner_style="bright_cyan",
        ) as status:
            for stream_mode, chunk in chat_agent.stream(
                dict(invocation),
                config=dict(config),
                stream_mode=["updates", "values"],
            ):
                if stream_mode == "values" and isinstance(chunk, Mapping):
                    final_state = chunk
                    continue
                if stream_mode == "updates":
                    status.update("[accent]Agent is working…[/accent]")
                    _print_activity_update(console, chunk)
                    if isinstance(chunk, Mapping):
                        for node_name, node_update in chunk.items():
                            response = _latest_ai_response(
                                _update_messages(node_update)
                            )
                            if response is not None:
                                streamed_response = response
                                if (
                                    isinstance(node_update, Mapping)
                                    and node_update.get("jump_to") == "end"
                                ):
                                    guardrail_response = _guardrail_stop_response(
                                        str(node_name),
                                        response,
                                    )
    finally:
        console.rule(style="bright_blue")

    if guardrail_response is not None:
        return guardrail_response

    final_messages = _update_messages(final_state)
    if final_messages:
        final_response = _latest_ai_response(final_messages[-1:])
        if final_response is not None:
            return final_response
    if streamed_response is not None:
        return streamed_response
    return response_text(final_messages)


def _database_label(database_url: str) -> str:
    database = database_url.rsplit("/", maxsplit=1)[-1]
    return database or database_url


def _print_banner(console: Console, *, thread_id: str) -> None:
    settings = get_settings()
    body = Text()
    body.append("Read-only SQLite research agent\n", style="assistant")
    body.append(f"Database: {_database_label(settings.database_url)}\n", style="muted")
    body.append(f"Model: {settings.model}\n", style="muted")
    body.append(f"Thread: {thread_id}\n", style="muted")
    body.append("Type /help for commands.", style="accent")
    console.print(
        Panel.fit(body, title="[accent]DB Agent[/accent]", border_style="cyan")
    )


def _print_help(console: Console) -> None:
    lines = [
        f"[accent]{command}[/accent]  {description}"
        for command, description in COMMANDS.items()
    ]
    console.print(
        Panel(
            "\n".join(lines),
            title="[accent]Commands[/accent]",
            border_style="cyan",
        )
    )


def _print_error(console: Console, message: str) -> None:
    console.print(
        Panel(
            Text(message, style="error"),
            title="[error]Error[/error]",
            border_style="red",
        )
    )


def run_chat(
    chat_agent: Any,
    *,
    console: Console,
    thread_id: str,
    recursion_limit: int,
) -> None:
    _print_banner(console, thread_id=thread_id)

    while True:
        try:
            user_input = Prompt.ask("[accent]You[/accent]", console=console).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[muted]Goodbye.[/muted]")
            return

        if not user_input:
            continue

        command = user_input.lower()
        if command in {"/exit", "/quit"}:
            console.print("[muted]Goodbye.[/muted]")
            return
        if command == "/help":
            _print_help(console)
            continue
        if command == "/clear":
            console.clear()
            _print_banner(console, thread_id=thread_id)
            continue
        if command == "/thread":
            console.print(f"[muted]Thread: {thread_id}[/muted]")
            continue
        if command == "/new":
            thread_id = str(uuid.uuid4())
            console.print(f"[assistant]Started a new conversation:[/assistant] {thread_id}")
            continue
        if command.startswith("/"):
            console.print("[warning]Unknown command. Type /help for options.[/warning]")
            continue

        if len(user_input) > MAX_INPUT_CHARACTERS:
            _print_error(
                console,
                f"Message is too long. The limit is {MAX_INPUT_CHARACTERS:,} characters.",
            )
            continue

        invocation: dict[str, Any] = {
            "messages": [{"role": "user", "content": user_input}],
        }

        config = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": recursion_limit,
        }

        try:
            answer = stream_agent_response(
                chat_agent,
                invocation,
                config,
                console=console,
            )
        except KeyboardInterrupt:
            console.print("\n[warning]Request cancelled.[/warning]")
            continue
        except GraphRecursionError:
            _print_error(
                console,
                f"The agent used all {recursion_limit} graph steps before finishing. "
                "Review the activity trace for repeated tool calls. If it was still "
                "making progress, restart with a larger value such as "
                f"--recursion-limit {recursion_limit * 2}.",
            )
            continue
        except PIIDetectionError:
            _print_error(
                console,
                "A credential-like value was detected. Remove it and try again.",
            )
            continue
        except Exception as error:  # noqa: BLE001 - CLI boundary
            _print_error(console, str(error) or type(error).__name__)
            continue

        console.print(
            Panel(
                Markdown(answer),
                title="[assistant]Assistant[/assistant]",
                border_style="green",
                padding=(1, 2),
            )
        )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    console = Console(theme=THEME)
    thread_id = args.thread_id or str(uuid.uuid4())

    try:
        from db_agent_skills.agent import agent
    except Exception as error:  # noqa: BLE001 - startup boundary
        _print_error(console, str(error) or type(error).__name__)
        return 1

    run_chat(
        agent,
        console=console,
        thread_id=thread_id,
        recursion_limit=args.recursion_limit,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
