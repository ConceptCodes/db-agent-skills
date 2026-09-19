from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.language_models import BaseLanguageModel

from db_agent_skills.config import DEFAULT_DATABASE_URL


def create_db_toolkit(
    model: BaseLanguageModel,
    database_url: str = DEFAULT_DATABASE_URL,
) -> SQLDatabaseToolkit:
    """Create SQL tools for the selected database and model."""
    database = SQLDatabase.from_uri(database_url)
    return SQLDatabaseToolkit(db=database, llm=model)
