# Chinook database audit

Audit performed on 2026-09-18 against `data/chinook.db`.

## Artifact fingerprint

- Size: 1,007,616 bytes
- SHA-256: `7651ba378ac2fcd0dfc3c66fb101f7a7eed3ba39a612ec642b96e20702061f15`
- Encoding: UTF-8
- Page size: 4,096 bytes
- Schema: 11 tables, 0 views, 0 triggers, 11 explicit foreign-key indexes

These findings apply only to the fingerprinted database artifact. Re-audit independently after replacing or modifying the file.

## Integrity and reconciliation

- `PRAGMA integrity_check` returns `ok`.
- `PRAGMA foreign_key_check` returns no violations.
- Every invoice has at least one line, and every customer has at least one invoice.
- Stored invoice totals match rounded line totals for all 412 invoices.
- Summed invoice totals and summed line revenue both equal 2,328.60.
- Every invoice line has quantity 1 and a unit price of either 0.99 or 1.99.
- No audited invoice total or line price is negative or zero, and no line quantity is nonpositive.
- Historical line prices currently match catalog prices, but queries should still use `InvoiceLine.UnitPrice` for historical attribution.
- Foreign-key actions are `NO ACTION`.
- `PRAGMA foreign_keys` is `0` on a new connection. The agent's connection is enforced as read-only and cannot perform writes.

## Scale and coverage

- Invoice dates: 2021-01-01 00:00:00 through 2025-12-22 00:00:00
- Customers: 59 across 24 countries; all assigned to one of three sales-support employees
- Invoices: 412, containing 1 through 14 lines and averaging 5.44 lines
- Invoice lines: 2,240
- Tracks: 3,503; 1,984 sold at least once and 1,519 never sold
- Artists: 275, including 71 with no albums
- Albums: 347; every album has at least one track
- Playlists: 18 containing 8,715 track memberships

## Interpretation findings

### Revenue semantics are limited

The database has sales prices and invoice totals but no currency, product cost, tax, freight, refund, payment-status, or exchange-rate fields. It supports revenue-style analysis, not profit or cash-collection conclusions.

### Audio and video share the `Track` table

`MediaType` includes audio encodings and protected MPEG-4 video. Track duration ranges from 1,071 to 5,286,953 milliseconds, so duration analysis must segment by media type.

### Labels are not identifiers

There are 199 duplicate track-name groups. Playlist names are also duplicated: `Music`, `Movies`, `TV Shows`, and `Audiobooks` each map to two different playlist IDs. Grouping only by these names merges distinct records.

### Playlist attribution overlaps

Every track belongs to at least two playlists, and some belong to five. The two `Music` playlists have identical 3,290-track memberships, while the two `TV Shows` playlists have identical 213-track memberships. Both copies of `Movies` and `Audiobooks` are empty. Playlist-attributed sales cannot be added into an overall total.

### Catalog coverage is uneven

Seventy-one artists have no albums, while all albums have tracks. Composer is missing for 977 tracks. Use left joins for catalog-completeness questions and inner joins for observed sales.

### Customer organization data is sparse

`Company` is missing for 49 customers and `State` for 29. Use customer IDs and personal names rather than company as the default customer identity.

## Schema and performance findings

- There are no views or triggers.
- Eleven explicit indexes cover all foreign-key columns, so ordinary relationship joins are indexed.
- There is no index on `InvoiceDate`, though the table has only 412 rows.
- The schema declares no `CHECK` constraints for positive prices, totals, quantities, byte counts, or durations. Existing data passes those checks, but future writes require validation.
