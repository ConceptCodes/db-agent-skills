# DB Agent Skills

A database research assistant built with [Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview), [OpenRouter](https://openrouter.ai/docs/quickstart), LangChain's SQL toolkit, SQLite, and database-specific Agent Skills.

The project pairs each database with a skill that teaches the agent its schema, correct business metrics, join behavior, known data-quality issues, and safe query patterns. It currently includes audited skills for Northwind and Chinook.

## What is included

| Database | Domain | Size | Skill |
| --- | --- | ---: | --- |
| Northwind | Customers, orders, products, inventory, shipping, and employees | 24 MB | [`skills/northwind`](skills/northwind/SKILL.md) |
| Chinook | Artists, albums, tracks, invoices, customers, and playlists | 984 KB | [`skills/chinook`](skills/chinook/SKILL.md) |

Each skill contains:

- `SKILL.md` with routing instructions and query invariants
- `references/schema.md` with the audited schema and relationships
- `references/query-guide.md` with grain-safe SQL patterns
- `references/audit.md` with integrity and data-quality findings
- `scripts/audit_*.py` for repeatable, read-only validation

The skill folders follow the format consumed by Deep Agents: a required `SKILL.md` plus optional supporting files. They do not require OpenAI-specific agent metadata.

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/) for dependency management
- An OpenRouter API key
- The `sqlite3` CLI is optional but useful for manual inspection

## Setup

Install the project dependencies:

```bash
uv sync
```

Create the local environment file and add an OpenRouter API key:

```bash
cp .env.example .env
# Edit .env and set OPENROUTER_API_KEY.
```

The default OpenRouter model slug is `openrouter:openai/gpt-5.6-luna`. Override it with any OpenRouter model that supports tool calling:

```bash
export DB_AGENT_MODEL="anthropic/claude-sonnet-4.5"
```

All model inference goes through LangChain's first-party OpenRouter integration, `ChatOpenRouter`. The project does not use `OPENAI_API_KEY` or call OpenAI's inference API directly; a slug beginning with `openai/` only selects an OpenAI model through OpenRouter.

## Select a database

Northwind is selected by default using an absolute path derived from the repository location.

To use Chinook instead, run this from the repository root:

```bash
export DB_AGENT_DATABASE_URL="sqlite:///${PWD}/data/chinook.db"
```

To switch back explicitly:

```bash
export DB_AGENT_DATABASE_URL="sqlite:///${PWD}/data/northwind.db"
```

`DB_AGENT_DATABASE_URL` can point to another SQLite fixture during testing. The selected database must match the skill whose schema assumptions are being used.

## Audit the databases

The audit scripts use SQLite's read-only URI mode, verify the expected schema, and emit JSON.

```bash
python3 skills/northwind/scripts/audit_northwind.py
python3 skills/chinook/scripts/audit_chinook.py
```

Audit another copy of the same database schema:

```bash
python3 skills/chinook/scripts/audit_chinook.py \
  --database /absolute/path/to/chinook-test.db
```

The scripts report the file checksum, integrity result, foreign-key violations, object and row counts, date coverage, reconciliation checks, and known data-quality indicators. They reject a database that does not contain the expected schema.

## How the agent is organized

- [`config.py`](src/db_agent_skills/config.py) loads the OpenRouter model, API key, and database URL from environment-backed settings.
- [`model.py`](src/db_agent_skills/model.py) creates the shared `ChatOpenRouter` instance.
- [`tools.py`](src/db_agent_skills/tools.py) creates the LangChain `SQLDatabase` and `SQLDatabaseToolkit`.
- [`prompts.py`](src/db_agent_skills/prompts.py) defines the read-first, bounded-query, no-guessing policy.
- [`agent.py`](src/db_agent_skills/agent.py) constructs the Deep Agent and points it at the project skills.
- `skills/` provides progressively loaded, database-specific domain knowledge.

The system prompt instructs the agent to inspect the selected database, load the applicable skill, verify join grain and date boundaries, and treat database contents as untrusted data before answering.

## Project structure

```text
.
├── data/
│   ├── chinook.db
│   └── northwind.db
├── skills/
│   ├── chinook/
│   │   ├── SKILL.md
│   │   ├── references/
│   │   └── scripts/
│   └── northwind/
│       ├── SKILL.md
│       ├── references/
│       └── scripts/
├── src/db_agent_skills/
│   ├── agent.py
│   ├── config.py
│   ├── model.py
│   ├── prompts.py
│   └── tools.py
├── pyproject.toml
└── uv.lock
```

## Adding another database

1. Place the SQLite file under `data/` or configure an absolute external path.
2. Audit its schema, relationships, date coverage, constraints, and data quality.
3. Add `skills/<database>/SKILL.md` with a precise activation description and the query invariants that affect correctness.
4. Put detailed schema, metric, and audit material under `references/`.
5. Add a deterministic, read-only audit helper under `scripts/` when the checks will be reused.
6. Set `DB_AGENT_DATABASE_URL` to the database's absolute SQLite URL and verify that the selected skill matches it.

## Safety notes

- The agent's prompt treats database access as read-only unless a user explicitly requests a specific mutation.
- The current SQLAlchemy database connection does not technically enforce read-only mode. Use a read-only SQLite URI or filesystem permissions before exposing the agent to untrusted users.
- Foreign-key enforcement is disabled by default on new SQLite connections. Enable `PRAGMA foreign_keys = ON` before any authorized write.
- User input should be bound as query parameters whenever the calling interface supports them.
- Database values and retrieved documents are data, not instructions for the agent or shell.

## Development status

The database files, skills, audit tooling, configuration, prompt, and initial agent construction are present. The command-line interface is not finished: `src/db_agent_skills/cli.py` is empty, and the declared `db-agent-skills` console entry point does not yet resolve to an implemented `main` function.

Until that entry point is implemented and the agent wiring is integration-tested, use the audit scripts directly and treat the Python agent modules as an active development scaffold.

## Dataset sources

- [Northwind SQLite3](https://github.com/jpwhite3/northwind-SQLite3)
- [Chinook Database](https://github.com/lerocha/chinook-database)
