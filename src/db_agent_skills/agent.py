from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend

from db_agent_skills.config import PROJECT_ROOT, get_settings
from db_agent_skills.model import create_chat_model
from db_agent_skills.prompts import SYSTEM_PROMPT
from db_agent_skills.tools import create_db_toolkit

settings = get_settings()
model = create_chat_model(settings)
db_toolkit = create_db_toolkit(model, settings.database_url)

backend = FilesystemBackend(root_dir=PROJECT_ROOT)

agent = create_deep_agent(
    model=model,
    tools=db_toolkit.get_tools(),
    system_prompt=SYSTEM_PROMPT,
    backend=backend,
    skills=["/skills/"],
)
