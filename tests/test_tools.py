import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from db_agent_skills.tools import create_read_only_database


class ReadOnlyDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)

        self.database_path = Path(self.temporary_directory.name) / "fixture.db"
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
            connection.execute("INSERT INTO items (name) VALUES (?)", ("original",))

        database_url = f"sqlite:///{self.database_path.as_posix()}"
        self.database = create_read_only_database(database_url)
        self.addCleanup(self.database._engine.dispose)

    def test_allows_reads(self) -> None:
        self.assertEqual(
            self.database.run("SELECT name FROM items ORDER BY id"),
            "[('original',)]",
        )
        self.assertEqual(self.database.run("PRAGMA query_only"), "[(1,)]")

    def test_parallel_reads_keep_active_connections_open(self) -> None:
        # Isolate the regression: the former pool can segfault the interpreter.
        script = textwrap.dedent('''
            import sys
            from concurrent.futures import ThreadPoolExecutor
            from threading import Barrier
            from db_agent_skills.tools import create_read_only_database

            db = create_read_only_database(sys.argv[1])
            try:
                for _ in range(3):
                    ready = Barrier(8, timeout=10)
                    def read(_):
                        with db._engine.connect() as connection:
                            ready.wait()
                            for _ in range(20):
                                assert connection.exec_driver_sql(
                                    "SELECT name FROM items"
                                ).scalar_one() == "original"
                            assert connection.exec_driver_sql(
                                "PRAGMA query_only"
                            ).scalar_one() == 1
                    with ThreadPoolExecutor(max_workers=8) as executor:
                        list(executor.map(read, range(8)))
            finally:
                db._engine.dispose()
        ''')
        result = subprocess.run(
            [sys.executable, "-X", "faulthandler", "-c", script,
             f"sqlite:///{self.database_path.as_posix()}"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_writes(self) -> None:
        with self.assertRaises(SQLAlchemyError):
            self.database.run("UPDATE items SET name = 'changed' WHERE id = 1")

        with sqlite3.connect(self.database_path) as connection:
            stored_name = connection.execute(
                "SELECT name FROM items WHERE id = 1"
            ).fetchone()

        self.assertEqual(stored_name, ("original",))

    def test_rejects_file_creating_sql(self) -> None:
        attached_path = Path(self.temporary_directory.name) / "attached.db"
        vacuumed_path = Path(self.temporary_directory.name) / "vacuumed.db"

        with self.assertRaises(SQLAlchemyError):
            self.database.run(
                f"ATTACH DATABASE '{attached_path.as_posix()}' AS attached"
            )
        with self.assertRaises(SQLAlchemyError):
            self.database.run(f"VACUUM INTO '{vacuumed_path.as_posix()}'")

        self.assertFalse(attached_path.exists())
        self.assertFalse(vacuumed_path.exists())

    def test_cannot_disable_query_only(self) -> None:
        with self.assertRaises(SQLAlchemyError):
            self.database.run("PRAGMA query_only = OFF")

        self.assertEqual(self.database.run("PRAGMA query_only"), "[(1,)]")

    def test_requires_file_backed_sqlite(self) -> None:
        with self.assertRaisesRegex(ValueError, "file-backed SQLite"):
            create_read_only_database("sqlite:///:memory:")

        with self.assertRaisesRegex(ValueError, "Only SQLite"):
            create_read_only_database("postgresql://localhost/example")


if __name__ == "__main__":
    unittest.main()
