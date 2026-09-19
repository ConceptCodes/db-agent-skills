# Northwind query guide

Use these patterns to preserve the correct business grain. Bind the named parameters through the calling library; replace them with quoted literals only in an interface that cannot bind values.

## Net sales over time

Net merchandise sales exclude freight and apply line discounts.

```sql
SELECT
    strftime('%Y-%m', o.OrderDate) AS order_month,
    COUNT(DISTINCT o.OrderID) AS order_count,
    ROUND(SUM(od.UnitPrice * od.Quantity * (1 - od.Discount)), 2) AS net_sales
FROM Orders AS o
JOIN "Order Details" AS od ON od.OrderID = o.OrderID
WHERE o.OrderDate >= :start_ts
  AND o.OrderDate < :end_ts
GROUP BY order_month
ORDER BY order_month;
```

Use `OrderDate` for booked sales and `ShippedDate` for shipped-sales analysis. Say which one was used.

## Order totals and freight

Freight is stored once per order. Aggregate line items before summing it.

```sql
WITH order_totals AS (
    SELECT
        o.OrderID,
        o.CustomerID,
        o.Freight,
        SUM(od.UnitPrice * od.Quantity * (1 - od.Discount)) AS net_sales
    FROM Orders AS o
    JOIN "Order Details" AS od ON od.OrderID = o.OrderID
    WHERE o.OrderDate >= :start_ts
      AND o.OrderDate < :end_ts
    GROUP BY o.OrderID, o.CustomerID, o.Freight
)
SELECT
    COUNT(*) AS order_count,
    ROUND(SUM(net_sales), 2) AS net_sales,
    ROUND(SUM(Freight), 2) AS freight,
    ROUND(AVG(net_sales), 2) AS average_order_value
FROM order_totals;
```

Do not sum `Orders.Freight` directly after joining to order lines.

## Customer sales

Group by the stable identifier as well as the display name. Two customer rows share the company name `IT`.

```sql
SELECT
    c.CustomerID,
    c.CompanyName,
    COUNT(DISTINCT o.OrderID) AS order_count,
    ROUND(SUM(od.UnitPrice * od.Quantity * (1 - od.Discount)), 2) AS net_sales
FROM Customers AS c
JOIN Orders AS o ON o.CustomerID = c.CustomerID
JOIN "Order Details" AS od ON od.OrderID = o.OrderID
WHERE o.OrderDate >= :start_ts
  AND o.OrderDate < :end_ts
GROUP BY c.CustomerID, c.CompanyName
ORDER BY net_sales DESC;
```

Use `Orders.ShipCountry` for destination analysis and `Customers.Country` for customer-account geography.

## Employee performance

```sql
SELECT
    e.EmployeeID,
    e.FirstName || ' ' || e.LastName AS employee_name,
    COUNT(DISTINCT o.OrderID) AS order_count,
    ROUND(SUM(od.UnitPrice * od.Quantity * (1 - od.Discount)), 2) AS net_sales
FROM Employees AS e
JOIN Orders AS o ON o.EmployeeID = e.EmployeeID
JOIN "Order Details" AS od ON od.OrderID = o.OrderID
GROUP BY e.EmployeeID, e.FirstName, e.LastName
ORDER BY net_sales DESC;
```

SQLite uses `||` for concatenation. The `Invoices.Salesperson` value is not usable.

## Shipping timeliness

```sql
SELECT
    COUNT(*) AS shipped_orders,
    SUM(datetime(ShippedDate) > datetime(RequiredDate)) AS late_orders,
    ROUND(
        100.0 * SUM(datetime(ShippedDate) > datetime(RequiredDate)) / COUNT(*),
        2
    ) AS late_rate_pct
FROM Orders
WHERE ShippedDate IS NOT NULL;
```

Keep unshipped orders separate from late shipped orders. The audited database has 21 unshipped orders.

## Inventory snapshot

```sql
SELECT
    p.ProductID,
    p.ProductName,
    c.CategoryName,
    p.UnitsInStock,
    p.UnitsOnOrder,
    p.ReorderLevel
FROM Products AS p
JOIN Categories AS c ON c.CategoryID = p.CategoryID
WHERE p.Discontinued = '0'
  AND p.UnitsInStock <= p.ReorderLevel
ORDER BY p.UnitsInStock, p.ProductID;
```

This identifies active products at or below their reorder level; it is not a historical stockout analysis. State whether `UnitsOnOrder` is considered when using another reorder definition.

## Join and aggregation checks

- `Orders` to `Order Details` is one-to-many; line joins multiply order-level columns.
- `Products` to `Order Details` is one-to-many; count products with `COUNT(DISTINCT ProductID)` after the join.
- `Employees` to `EmployeeTerritories` is one-to-many; joining territories into employee sales can multiply sales unless territories are aggregated separately.
- Customer and supplier names are not keys. Preserve `CustomerID` or `SupplierID` in grouped results.
- Round for presentation after aggregation, not each line before summing.
- Use `NULLIF` around denominators when a filtered group might be empty.

## Performance

The 609,283-row `Order Details` table and 16,282-row `Orders` table have no explicit secondary indexes. Filter early, select only needed columns, and inspect expensive queries with `EXPLAIN QUERY PLAN`. Do not add indexes to the bundled artifact unless the user asks to change it; use a copied fixture for experiments.
