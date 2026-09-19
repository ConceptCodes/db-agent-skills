# Northwind schema

This reference describes the audited `data/northwind.db` artifact, not every Northwind variant found online.

## Relationship map

```text
Customers 1 ── * Orders * ── 1 Employees
                       * ── 1 Shippers
Orders    1 ── * Order Details * ── 1 Products
                                      * ── 1 Categories
                                      * ── 1 Suppliers

Employees 1 ── * Employees          via ReportsTo
Employees 1 ── * EmployeeTerritories * ── 1 Territories * ── 1 Regions

Customers 1 ── * CustomerCustomerDemo * ── 1 CustomerDemographics
```

The customer-demographic branch is structurally present but both tables are empty.

## Tables and grain

| Table | Rows | Grain and useful fields |
| --- | ---: | --- |
| `Categories` | 8 | One category. PK `CategoryID`; name, description, picture. |
| `Customers` | 93 | One customer. Text PK `CustomerID`; company, contact, address, country. |
| `Employees` | 9 | One employee. PK `EmployeeID`; name, title, dates, address; self-FK `ReportsTo`. |
| `Shippers` | 3 | One shipping company. PK `ShipperID`. |
| `Suppliers` | 29 | One supplier. PK `SupplierID`; company, contact, address, country. |
| `Products` | 77 | One product. PK `ProductID`; FKs `SupplierID`, `CategoryID`; current price and inventory fields. |
| `Orders` | 16,282 | One order. PK `OrderID`; customer, employee, shipper, dates, freight, and `Ship*` destination fields. |
| `Order Details` | 609,283 | One product line per order. Composite PK (`OrderID`, `ProductID`); historical unit price, quantity, discount. |
| `Regions` | 4 | One sales region. PK `RegionID`. |
| `Territories` | 53 | One sales territory. Text PK `TerritoryID`; FK `RegionID`. |
| `EmployeeTerritories` | 49 | Employee-to-territory bridge. Composite PK (`EmployeeID`, `TerritoryID`). |
| `CustomerDemographics` | 0 | Customer-type lookup. Text PK `CustomerTypeID`. |
| `CustomerCustomerDemo` | 0 | Customer-to-type bridge. Composite PK (`CustomerID`, `CustomerTypeID`). |

Row counts are the audited counts for SHA-256 `2f4f5c68dfcd33ba27373eae48c7a4869800c68095ee0f9f0da494f83382a877`.

## Central-table columns

### `Orders`

- Identifiers: `OrderID`, `CustomerID`, `EmployeeID`, `ShipVia`
- Timestamps: `OrderDate`, `RequiredDate`, `ShippedDate`
- Order-level amount: `Freight`
- Delivery snapshot: `ShipName`, `ShipAddress`, `ShipCity`, `ShipRegion`, `ShipPostalCode`, `ShipCountry`

`CustomerID`, `EmployeeID`, and `ShipVia` are populated for every audited order. `ShippedDate` is null for 21 orders.

### `Order Details`

- Key: (`OrderID`, `ProductID`)
- Measures: `UnitPrice`, `Quantity`, `Discount`
- Checks: `UnitPrice >= 0`, `Quantity > 0`, and `0 <= Discount <= 1`

Use this table for historical sales. Its `UnitPrice` is the price captured on the order line.

### `Products`

- Classification: `SupplierID`, `CategoryID`
- Current snapshot: `UnitPrice`, `UnitsInStock`, `UnitsOnOrder`, `ReorderLevel`
- Status: `Discontinued`, stored as text values `'0'` and `'1'`

All audited products have a supplier and category. Eight products are discontinued.

## Views

The database has 17 views. Prefer base tables for new analysis because several views preserve Access or SQL Server idioms.

| View or group | Audited behavior |
| --- | --- |
| `Order Details Extended` | Adds product name and computed line `ExtendedPrice`; 609,283 rows. |
| `Order Subtotals` | Correctly aggregates net line sales to one row per order; 16,282 rows. |
| `Orders Qry` | Joins orders to customer details; 16,282 rows. |
| `Invoices` | Line-grain denormalized view; 609,283 rows. Its `Salesperson` expression is broken in SQLite and always returns integer `0`. |
| `ProductDetails_V` | Product with category and supplier details; 77 rows. |
| `Alphabetical list of products`, `Current Product List`, `Products by Category` | Active-product views; each returns 69 rows. |
| `Products Above Average Price` | Current products priced above the overall current average; 25 rows. |
| `Customer and Suppliers by City` | Union of customers and suppliers; 122 rows. |
| `Summary of Sales by Quarter`, `Summary of Sales by Year` | Despite their names, these do not group by quarter or year. Each returns one row per shipped order. |
| `Category Sales for 1997`, `Product Sales for 1997`, `Quarterly Orders`, `Sales Totals by Amount`, `Sales by Category` | Hard-code 1997 and return zero rows because this artifact's orders start in 2012. |

## SQLite-specific details

- Dates use `TEXT` storage even where the declared type is `DATE` or `DATETIME`.
- Names with spaces require double quotes or square brackets.
- Integer primary keys use SQLite rowids. The only physical indexes are automatic primary-key indexes for text or composite keys.
- Foreign keys are declared and currently valid, but enforcement is disabled by default for a new SQLite connection.
