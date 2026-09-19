import os

from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware
from langgraph.checkpoint.memory import InMemorySaver

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

agent = create_deep_agent(
    model=settings.model,
    tools=db_toolkit.get_tools(),
    system_prompt=SYSTEM_PROMPT,
    middleware=[TodoListMiddleware()],
    skills=["/skills/"],
    checkpointer=checkpointer,
    name="db_agent",
)
