import sqlite3
from collections.abc import Callable
from pathlib import Path

from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_community.utilities import SQLDatabase
from langchain_core.language_models import BaseLanguageModel
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.pool import QueuePool

from db_agent_skills.config import DEFAULT_DATABASE_URL


_DENIED_SQLITE_ACTIONS = frozenset(
    {
        sqlite3.SQLITE_ALTER_TABLE,
        sqlite3.SQLITE_ANALYZE,
        sqlite3.SQLITE_ATTACH,
        sqlite3.SQLITE_CREATE_INDEX,
        sqlite3.SQLITE_CREATE_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_INDEX,
        sqlite3.SQLITE_CREATE_TEMP_TABLE,
        sqlite3.SQLITE_CREATE_TEMP_TRIGGER,
        sqlite3.SQLITE_CREATE_TEMP_VIEW,
        sqlite3.SQLITE_CREATE_TRIGGER,
        sqlite3.SQLITE_CREATE_VIEW,
        sqlite3.SQLITE_CREATE_VTABLE,
        sqlite3.SQLITE_DELETE,
        sqlite3.SQLITE_DETACH,
        sqlite3.SQLITE_DROP_INDEX,
        sqlite3.SQLITE_DROP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_INDEX,
        sqlite3.SQLITE_DROP_TEMP_TABLE,
        sqlite3.SQLITE_DROP_TEMP_TRIGGER,
        sqlite3.SQLITE_DROP_TEMP_VIEW,
        sqlite3.SQLITE_DROP_TRIGGER,
        sqlite3.SQLITE_DROP_VIEW,
        sqlite3.SQLITE_DROP_VTABLE,
        sqlite3.SQLITE_INSERT,
        sqlite3.SQLITE_REINDEX,
        sqlite3.SQLITE_UPDATE,
    }
)

_READ_ONLY_PRAGMAS_WITH_ARGUMENTS = frozenset(
    {
        "foreign_key_check",
        "foreign_key_list",
        "index_info",
        "index_list",
        "index_xinfo",
        "integrity_check",
        "quick_check",
        "table_info",
        "table_xinfo",
    }
)

_READ_ONLY_PRAGMAS_WITHOUT_ARGUMENTS = frozenset(
    {
        "application_id",
        "collation_list",
        "compile_options",
        "data_version",
        "database_list",
        "encoding",
        "foreign_keys",
        "freelist_count",
        "function_list",
        "journal_mode",
        "module_list",
        "page_count",
        "page_size",
        "pragma_list",
        "query_only",
        "read_uncommitted",
        "schema_version",
        "table_list",
        "user_version",
    }
)

_DENIED_SQLITE_FUNCTIONS = frozenset({"load_extension", "readfile", "writefile"})


def _read_only_authorizer(
    action_code: int,
    argument_1: str | None,
    argument_2: str | None,
    _database_name: str | None,
    _trigger_name: str | None,
) -> int:
    if action_code in _DENIED_SQLITE_ACTIONS:
        return sqlite3.SQLITE_DENY

    if action_code == sqlite3.SQLITE_PRAGMA:
        pragma_name = (argument_1 or "").lower()
        if pragma_name in _READ_ONLY_PRAGMAS_WITH_ARGUMENTS:
            return sqlite3.SQLITE_OK
        if (
            pragma_name in _READ_ONLY_PRAGMAS_WITHOUT_ARGUMENTS
            and argument_2 is None
        ):
            return sqlite3.SQLITE_OK
        return sqlite3.SQLITE_DENY

    if action_code == sqlite3.SQLITE_FUNCTION:
        function_name = (argument_2 or argument_1 or "").lower()
        if function_name in _DENIED_SQLITE_FUNCTIONS:
            return sqlite3.SQLITE_DENY

    return sqlite3.SQLITE_OK


def _read_only_connection_factory(database_url: str) -> Callable[[], sqlite3.Connection]:
    url = make_url(database_url)
    if url.get_backend_name() != "sqlite":
        raise ValueError("Only SQLite database URLs are supported.")
    if not url.database or url.database == ":memory:":
        raise ValueError("A file-backed SQLite database is required.")

    database_path = Path(url.database).expanduser().resolve(strict=True)
    if not database_path.is_file():
        raise ValueError(f"SQLite database path is not a file: {database_path}")

    read_only_uri = f"{database_path.as_uri()}?mode=ro"

    def connect() -> sqlite3.Connection:
        connection = sqlite3.connect(
            read_only_uri,
            uri=True,
            check_same_thread=False,
        )
        connection.execute("PRAGMA query_only = ON")
        connection.enable_load_extension(False)
        connection.set_authorizer(_read_only_authorizer)
        return connection

    return connect


def create_read_only_database(
    database_url: str = DEFAULT_DATABASE_URL,
) -> SQLDatabase:
    """Create a SQLDatabase whose SQLite connections cannot mutate the file."""
    engine = create_engine(
        "sqlite+pysqlite://",
        creator=_read_only_connection_factory(database_url),
        # The creator opens a file, but the empty URL defaults to SingletonThreadPool,
        # which can evict active connections as agent worker threads change.
        poolclass=QueuePool,
    )
    return SQLDatabase(engine)


def create_db_toolkit(
    model: BaseLanguageModel,
    database_url: str = DEFAULT_DATABASE_URL,
) -> SQLDatabaseToolkit:
    """Create SQL tools for the selected database and model."""
    database = create_read_only_database(database_url)
    return SQLDatabaseToolkit(db=database, llm=model)
