---
name: chinook
description: Query, explain, and audit the bundled Chinook SQLite database for media catalog, invoices, customers, employee support, genres, and playlists. Use for Chinook questions or SQL targeting data/chinook.db; do not apply its schema assumptions to Northwind or unrelated databases.
---

# Chinook SQLite

Use the repository's `data/chinook.db` as the canonical Chinook artifact. Resolve it from the repository root, not from the process working directory. The application can select another database through `DB_AGENT_DATABASE_URL`; confirm the selected database is Chinook before relying on this skill's schema facts.

Database access is read-only. Use `SELECT`, `WITH`, `EXPLAIN QUERY PLAN`, and non-mutating PRAGMAs. Do not attempt data or schema changes.

## Route the task

- Read [references/schema.md](references/schema.md) before writing joins or choosing tables.
- Read [references/query-guide.md](references/query-guide.md) for revenue, customer, artist, genre, employee, track, or playlist analysis.
- Read [references/audit.md](references/audit.md) for data-quality, integrity, provenance, or limitation questions.

## Query invariants

- Treat `Invoice` as one row per invoice and `InvoiceLine` as one purchased track per invoice line.
- For catalog-attributed sales, calculate revenue from historical line values: `InvoiceLine.UnitPrice * InvoiceLine.Quantity`.
- Use `Invoice.Total` only at invoice grain. Do not sum it after joining to `InvoiceLine`, which would multiply the total by the number of lines.
- Keep `Quantity` in calculations even though every audited line currently has quantity 1.
- Reach artists through `Track -> Album -> Artist`; reach support representatives through `Invoice -> Customer -> Employee`.
- Preserve IDs when grouping. Track names are not unique, and four playlist names are duplicated.
- Treat playlist attribution as non-additive: a track can belong to several playlists, so sales joined through `PlaylistTrack` may be counted in each applicable playlist.
- Use half-open timestamp ranges such as `InvoiceDate >= :start_ts AND InvoiceDate < :end_ts`. SQLite stores these timestamps as text.
- Distinguish current catalog price `Track.UnitPrice` from historical sale price `InvoiceLine.UnitPrice`.
- Filter or group by `MediaType` before interpreting duration: the catalog contains both audio and video.
- Do not infer currency, cost, profit, tax, refunds, or payment status. The schema supplies none of those semantics.

## Produce trustworthy answers

State the metric definition, invoice date range, and grain when they affect interpretation. Check join multiplicity before aggregating, retain identifiers alongside display names, and mention relevant limitations from the audit. Keep exploratory output bounded with aggregation or `LIMIT`.

Parameterize externally supplied values whenever the query interface supports parameters. Never interpolate user-provided values into SQL strings.
