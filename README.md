# DB Agent w/ Skills

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

The default model is `openrouter:openai/gpt-5.6-luna`. The `openrouter:` prefix tells LangChain to resolve the model through `ChatOpenRouter`; the remainder is the OpenRouter model ID. Override it with any OpenRouter model that supports tool calling:

```bash
export DB_AGENT_MODEL="openrouter:anthropic/claude-sonnet-4.5"
```

## Chat with the agent

Start the colorful interactive CLI:

```bash
uv run db-agent-skills
```

The CLI streams an activity trace showing graph steps, tool calls, bounded tool arguments, and bounded tool results, then renders the final agent response as Markdown. It does not display private model reasoning. Conversation state remains in memory. Use `/help` to list commands, `/new` to start a fresh thread, and `/exit` to quit.

Skill-guided database research can require several model and tool steps, so the CLI uses a finite 50-step budget by default. If a valid complex request is still progressing when it reaches that guardrail, restart with a higher limit:

```bash
uv run db-agent-skills --recursion-limit 100
```

### Sample questions

With the default Northwind database:

- What tables and date ranges are available in this database?
- Who were the top five customers by revenue, and how did you calculate revenue?
- Show monthly revenue for 1997 and call out the strongest and weakest months.
- Which products have never been ordered?
- Compare each employee's order count and revenue. Avoid double-counting orders.
- Which orders shipped late, and which shipping countries had the highest late-shipment rate?
- Check the database for orphaned foreign keys or suspicious data-quality issues.
- Explain the query plan for a revenue-by-category report and suggest safe indexing improvements.

To try Chinook, restart the CLI after selecting its database:

```bash
export DB_AGENT_DATABASE_URL="sqlite:///${PWD}/data/chinook.db"
uv run db-agent-skills
```

Then ask:

- Which artists generated the most invoice-line revenue?
- What are the top genres by revenue and unique customers?
- Compare customer spending by country without counting an invoice more than once.
- Which tracks appear in the most playlists?
- Are invoice totals consistent with their invoice lines?
- Summarize the schema and explain the correct join path from customers to tracks.

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

## How the agent is organized

- [`config.py`](src/db_agent_skills/config.py) loads the OpenRouter model, API key, and database URL from environment-backed settings.
- [`model.py`](src/db_agent_skills/model.py) resolves the SQL toolkit's query-checker model.
- [`tools.py`](src/db_agent_skills/tools.py) creates the LangChain `SQLDatabase` and `SQLDatabaseToolkit`.
- [`prompts.py`](src/db_agent_skills/prompts.py) defines the read-first, bounded-query, no-guessing policy.
- [`guardrails.py`](src/db_agent_skills/guardrails.py) rejects requests outside read-only database research, limits model and tool calls, and filters sensitive data.
- [`backend.py`](src/db_agent_skills/backend.py) mounts bundled skills at `/skills/`, denies agent file-tool writes there, and keeps other agent files in state.
- [`agent.py`](src/db_agent_skills/agent.py) constructs the Deep Agent with the project skill source and an in-memory checkpointer.
- `skills/` provides progressively loaded, database-specific domain knowledge.

The system prompt instructs the agent to inspect the selected database, load the applicable skill, verify join grain and date boundaries, and treat database contents as untrusted data before answering.

Deep Agents handles skill discovery and progressive loading through the agent's `skills=["/skills/"]` configuration and the composite backend's restricted `/skills/` mount; the CLI does not duplicate that behavior.
The main model remains a provider-qualified string passed to `create_deep_agent`; the SQL query checker and scope classifier share a separate instance because they require a `BaseLanguageModel` object.

## Project structure

```text
.
├── data/
│   ├── chinook.db
│   └── northwind.db
├── skills/
│   ├── chinook/
│   │   ├── SKILL.md
│   │   └── references/
│   └── northwind/
│       ├── SKILL.md
│       └── references/
├── src/db_agent_skills/
│   ├── agent.py
│   ├── backend.py
│   ├── config.py
│   ├── constants.py
│   ├── guardrails.py
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
5. Set `DB_AGENT_DATABASE_URL` to the database's absolute SQLite URL and verify that the selected skill matches it.

## Safety notes

- SQLite connections use URI `mode=ro`, `PRAGMA query_only = ON`, and a SQLite authorizer that rejects mutations, database attachment, and file-oriented functions.
- Host-filesystem access is restricted to the bundled `/skills/` mount, and file-tool writes to that mount are denied. Other agent files use the in-memory state backend.
- A fail-closed scope classifier rejects unrelated requests before the main agent or database tools run. It uses one structured model call with bounded recent context per user message, preserving database follow-ups while rejecting classification failures.
- LangChain middleware limits each request to 16 model calls and 24 tool calls. If either limit is reached, the activity trace marks the guardrail stop and the CLI explains which limit ended the request.
- Credential-like values are blocked in user input and redacted from tool results and model output. Valid payment-card numbers are masked.
- Conversation checkpoints are held in memory and are lost when the process exits.
- User input should be bound as query parameters whenever the calling interface supports them.
- Database values and retrieved documents are data, not instructions for the agent or shell.

## Development status

The database files, skills, configuration, prompt, read-only SQL tooling, and interactive CLI are present. The CLI is intended for local agent testing; its in-memory conversations are not durable across process restarts.

## Dataset sources

- [Northwind SQLite3](https://github.com/jpwhite3/northwind-SQLite3)
- [Chinook Database](https://github.com/lerocha/chinook-database)
