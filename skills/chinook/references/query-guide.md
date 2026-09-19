# Chinook query guide

Use these patterns to preserve the correct business grain. Bind the named parameters through the calling library; replace them with quoted literals only in an interface that cannot bind values.

## Invoice-level revenue over time

Use stored invoice totals when no catalog dimension is needed.

```sql
SELECT
    strftime('%Y-%m', InvoiceDate) AS invoice_month,
    COUNT(*) AS invoice_count,
    COUNT(DISTINCT CustomerId) AS customer_count,
    ROUND(SUM(Total), 2) AS revenue
FROM Invoice
WHERE InvoiceDate >= :start_ts
  AND InvoiceDate < :end_ts
GROUP BY invoice_month
ORDER BY invoice_month;
```

The schema does not identify a currency. Label the result as revenue or monetary units unless the user supplies a currency assumption.

## Customer revenue

Remain at invoice grain; joining lines is unnecessary.

```sql
SELECT
    c.CustomerId,
    c.FirstName || ' ' || c.LastName AS customer_name,
    COUNT(i.InvoiceId) AS invoice_count,
    ROUND(SUM(i.Total), 2) AS revenue
FROM Customer AS c
JOIN Invoice AS i ON i.CustomerId = c.CustomerId
WHERE i.InvoiceDate >= :start_ts
  AND i.InvoiceDate < :end_ts
GROUP BY c.CustomerId, c.FirstName, c.LastName
ORDER BY revenue DESC;
```

Use `Invoice.BillingCountry` for billed-sales geography and `Customer.Country` for the customer's current profile.

## Artist, album, or genre sales

Use invoice lines when attributing sales to catalog dimensions.

```sql
SELECT
    ar.ArtistId,
    ar.Name AS artist_name,
    COUNT(DISTINCT i.InvoiceId) AS invoice_count,
    SUM(il.Quantity) AS units,
    ROUND(SUM(il.UnitPrice * il.Quantity), 2) AS revenue
FROM Artist AS ar
JOIN Album AS al ON al.ArtistId = ar.ArtistId
JOIN Track AS t ON t.AlbumId = al.AlbumId
JOIN InvoiceLine AS il ON il.TrackId = t.TrackId
JOIN Invoice AS i ON i.InvoiceId = il.InvoiceId
WHERE i.InvoiceDate >= :start_ts
  AND i.InvoiceDate < :end_ts
GROUP BY ar.ArtistId, ar.Name
ORDER BY revenue DESC;
```

Swap the grouped dimension for `Album`, `Genre`, `Track`, or `MediaType` while retaining its ID. Do not sum `Invoice.Total` in this join.

## Support representative performance

```sql
SELECT
    e.EmployeeId,
    e.FirstName || ' ' || e.LastName AS support_rep,
    COUNT(DISTINCT c.CustomerId) AS customers,
    COUNT(i.InvoiceId) AS invoices,
    ROUND(SUM(i.Total), 2) AS revenue
FROM Employee AS e
JOIN Customer AS c ON c.SupportRepId = e.EmployeeId
JOIN Invoice AS i ON i.CustomerId = c.CustomerId
WHERE i.InvoiceDate >= :start_ts
  AND i.InvoiceDate < :end_ts
GROUP BY e.EmployeeId, e.FirstName, e.LastName
ORDER BY revenue DESC;
```

Only three employees are sales-support representatives in the audited data. Keep zero-customer employees with left joins when analyzing the whole organization.

## Unsold catalog items

```sql
SELECT
    t.TrackId,
    t.Name AS track_name,
    al.AlbumId,
    al.Title AS album_title,
    ar.ArtistId,
    ar.Name AS artist_name
FROM Track AS t
JOIN Album AS al ON al.AlbumId = t.AlbumId
JOIN Artist AS ar ON ar.ArtistId = al.ArtistId
LEFT JOIN InvoiceLine AS il ON il.TrackId = t.TrackId
WHERE il.InvoiceLineId IS NULL
ORDER BY ar.Name, al.Title, t.TrackId;
```

The audited database has 1,519 tracks with no invoice line.

## Playlist analysis

Always identify playlists by `PlaylistId`, because names are duplicated.

```sql
SELECT
    p.PlaylistId,
    p.Name,
    COUNT(pt.TrackId) AS track_count
FROM Playlist AS p
LEFT JOIN PlaylistTrack AS pt ON pt.PlaylistId = p.PlaylistId
GROUP BY p.PlaylistId, p.Name
ORDER BY p.PlaylistId;
```

A track's sale can be attributed to every playlist containing it. Do not add revenue across playlists and describe playlist revenue as overlapping attribution.

## Duration analysis

Convert milliseconds explicitly and include media type.

```sql
SELECT
    mt.MediaTypeId,
    mt.Name AS media_type,
    COUNT(*) AS tracks,
    ROUND(AVG(t.Milliseconds) / 60000.0, 2) AS average_minutes
FROM Track AS t
JOIN MediaType AS mt ON mt.MediaTypeId = t.MediaTypeId
GROUP BY mt.MediaTypeId, mt.Name
ORDER BY mt.MediaTypeId;
```

Video tracks average much longer than audio tracks, so an unfiltered catalog-wide average is usually misleading.

## Join and aggregation checks

- `Invoice` to `InvoiceLine` is one-to-many; joining lines multiplies invoice-level columns.
- `Artist` to `Album` and `Album` to `Track` are one-to-many; use distinct counts at the requested grain.
- `Track` to `Playlist` is many-to-many; playlist joins intentionally duplicate a track across playlists.
- Names are display attributes, not keys. Preserve IDs in grouped results.
- Round for presentation after aggregation, not each line before summing.
- Use `NULLIF` around denominators when a filtered group might be empty.
