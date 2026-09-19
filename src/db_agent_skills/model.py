from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel

from db_agent_skills.config import Settings, get_settings


def create_chat_model(settings: Settings | None = None) -> BaseChatModel:
    """Resolve the provider model used by the SQL toolkit's query checker."""
    resolved_settings = settings or get_settings()
    api_key = resolved_settings.openrouter_api_key

    if api_key is None or not api_key.get_secret_value().strip():
        raise RuntimeError(
            "OPENROUTER_API_KEY is required to create the database agent model."
        )

    return init_chat_model(
        resolved_settings.model,
        api_key=api_key.get_secret_value(),
        temperature=0,
    )
