---
name: northwind
description: Query, explain, and audit the bundled Northwind SQLite database for sales, orders, customers, products, suppliers, inventory, shipping, and employees. Use for Northwind questions or SQL targeting data/northwind.db; do not apply its schema assumptions to Chinook or unrelated databases.
---

# Northwind SQLite

Use the repository's `data/northwind.db` as the canonical Northwind artifact. Resolve it from the repository root, not from the process working directory. The application can select another database through `DB_AGENT_DATABASE_URL`; confirm the selected database is Northwind before relying on this skill's schema facts.

Database access is read-only. Use `SELECT`, `WITH`, `EXPLAIN QUERY PLAN`, and non-mutating PRAGMAs. Do not attempt data or schema changes.

## Route the task

- Read [references/schema.md](references/schema.md) before writing joins or choosing tables.
- Read [references/query-guide.md](references/query-guide.md) for sales, order, customer, shipping, employee, or inventory analysis.
- Read [references/audit.md](references/audit.md) for data-quality, integrity, performance, provenance, or legacy-view questions.

## Query invariants

- Quote identifiers containing spaces, especially `"Order Details"` and the legacy view names.
- Treat `Orders` as one row per order and `"Order Details"` as one row per order-product pair.
- Calculate net merchandise sales from historical line values: `UnitPrice * Quantity * (1 - Discount)`. Do not substitute the current `Products.UnitPrice`.
- Aggregate line items to order grain before combining them with `Orders.Freight`; otherwise freight is multiplied by the number of lines.
- After joining order lines, count orders with `COUNT(DISTINCT OrderID)` or pre-aggregate by order.
- Treat `Discount` as a fraction from 0 through 1, not a percentage from 0 through 100.
- Use half-open timestamp ranges such as `OrderDate >= :start_ts AND OrderDate < :end_ts`. The date columns are ISO-like text timestamps.
- Use `||` for SQLite string concatenation. Do not copy the `Invoices` view's broken `+` expression for salesperson names.
- Prefer base tables or dynamically dated queries over the legacy views that hard-code 1997.
- Treat `Products` inventory fields as a current snapshot; this database has no inventory-event history.
- Distinguish customer address fields from `Orders.Ship*` fields, which describe the order's delivery destination.

## Produce trustworthy answers

State the metric definition, time field, date range, and grain when they affect interpretation. Check join multiplicity before aggregating, preserve identifiers alongside names, and mention relevant data limitations from the audit. Keep exploratory output bounded with aggregation or `LIMIT`.

Parameterize externally supplied values whenever the query interface supports parameters. Never interpolate user-provided values into SQL strings.
