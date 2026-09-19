import os

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver

from db_agent_skills.backend import (
    SKILLS_SOURCE,
    create_agent_backend,
    create_agent_permissions,
)
from db_agent_skills.config import get_settings
from db_agent_skills.model import create_chat_model
from db_agent_skills.prompts import SYSTEM_PROMPT
from db_agent_skills.tools import create_db_toolkit

settings = get_settings()
api_key = settings.openrouter_api_key
if api_key is not None:
    os.environ.setdefault("OPENROUTER_API_KEY", api_key.get_secret_value())

toolkit_model = create_chat_model(settings)
db_toolkit = create_db_toolkit(toolkit_model, settings.database_url)

checkpointer = InMemorySaver()
backend = create_agent_backend()

agent = create_deep_agent(
    model=settings.model,
    tools=db_toolkit.get_tools(),
    system_prompt=SYSTEM_PROMPT,
    skills=[SKILLS_SOURCE],
    backend=backend,
    permissions=create_agent_permissions(),
    checkpointer=checkpointer,
    name="db_agent",
)
