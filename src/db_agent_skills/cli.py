from __future__ import annotations

import argparse
import uuid
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import BaseMessage
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text
from rich.theme import Theme

from db_agent_skills.config import get_settings


MAX_INPUT_CHARACTERS = 8_000
DEFAULT_RECURSION_LIMIT = 25

THEME = Theme(
    {
        "accent": "bold bright_cyan",
        "assistant": "bold bright_green",
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

    text = messages[-1].text.strip()
    return text or "The agent returned an empty response."


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
            with console.status(
                "[accent]Researching the database…[/accent]",
                spinner="dots",
                spinner_style="bright_cyan",
            ):
                result = chat_agent.invoke(invocation, config=config)
        except KeyboardInterrupt:
            console.print("\n[warning]Request cancelled.[/warning]")
            continue
        except Exception as error:  # noqa: BLE001 - CLI boundary
            _print_error(console, str(error) or type(error).__name__)
            continue

        answer = response_text(result.get("messages", []))
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
