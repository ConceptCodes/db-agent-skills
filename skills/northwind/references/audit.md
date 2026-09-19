# Northwind database audit

Audit performed on 2026-09-18 against `data/northwind.db`.

## Artifact fingerprint

- Size: 24,702,976 bytes
- SHA-256: `2f4f5c68dfcd33ba27373eae48c7a4869800c68095ee0f9f0da494f83382a877`
- Encoding: UTF-8
- Page size: 4,096 bytes
- Schema: 13 tables, 17 views, 0 triggers, 0 explicit secondary indexes

These findings apply only to the fingerprinted database artifact. Re-audit independently after replacing or modifying the file.

## Integrity and constraints

- `PRAGMA integrity_check` returns `ok`.
- `PRAGMA foreign_key_check` returns no violations.
- All orders have a customer, employee, shipper, and at least one order line.
- Every product appears in order history; every customer and employee has orders.
- `Order Details` enforces nonnegative price, positive quantity, and discounts from 0 through 1.
- Product price and inventory fields have nonnegative checks.
- Foreign-key actions are `NO ACTION`.
- `PRAGMA foreign_keys` is `0` on a new connection. The agent's connection is enforced as read-only and cannot perform writes.

## Scale and coverage

- Orders: 16,282, with contiguous IDs 10248 through 26529
- Order lines: 609,283, averaging 37.42 and ranging from 1 through 77 lines per order
- Order dates: 2012-07-10 15:40:46 through 2023-10-28 00:09:48
- Shipment dates: 2012-07-13 21:20:47 through 2023-11-19 02:55:24
- Unshipped orders: 21
- Late shipped orders: 3,755
- Products: 77, including 8 discontinued products
- Audited net merchandise sales: 448,386,633.17 using historical line prices and discounts

This is a generated, enlarged Northwind variant rather than the small canonical tutorial dataset. Do not import row-count or date assumptions from other Northwind copies.

## Correctness findings

### Broken salesperson value in `Invoices`

The view uses:

```sql
Employees.FirstName + ' ' + Employees.LastName
```

SQLite treats `+` as numeric addition, so every audited `Salesperson` value is integer `0`. Join `Orders.EmployeeID` to `Employees` and concatenate with `||` instead.

### Legacy 1997 views are empty

Five views filter to 1997 even though this database starts in 2012:

- `Category Sales for 1997`
- `Product Sales for 1997`
- `Quarterly Orders`
- `Sales Totals by Amount`
- `Sales by Category`

Each returns zero rows. Use base tables with a requested or data-driven date range.

### Misleading summary-view names

`Summary of Sales by Quarter` and `Summary of Sales by Year` do not aggregate by quarter or year. They return `ShippedDate`, `OrderID`, and subtotal for each shipped order. Aggregate explicitly with `strftime` when a time summary is requested.

### Sparse customer records and duplicate display name

Customers `Val2 ` (the ID contains a trailing space) and `VALON` both use company name `IT` and lack address, city, and country values. Together they have 335 orders. Group and join customers by exact `CustomerID`, not `CompanyName`, and do not silently trim identifiers.

### Empty demographic branch

`CustomerDemographics` and `CustomerCustomerDemo` contain no rows. They cannot support customer-segmentation conclusions.

## Performance findings

There are no explicit secondary indexes, including on foreign keys or order dates. A representative date-filtered sales query scans all 609,283 order lines and looks up orders by integer primary key before grouping. Use bounded filters and query plans for interactive analysis. Treat index creation as a deliberate database modification and test it on a copy.

## Validated calculations

- `Order Subtotals` matches a direct aggregation of `Order Details` within `0.000001` for every order.
- No order has a required date before its order date.
- No shipped order has a shipment timestamp before its order timestamp.
- Freight has no negative values.
- Product and order foreign-key columns used by the main sales model are populated.
