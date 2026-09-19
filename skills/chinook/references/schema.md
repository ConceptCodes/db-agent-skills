# Chinook schema

This reference describes the audited `data/chinook.db` artifact, not every Chinook variant found online.

## Relationship map

```text
Artist 1 ── * Album 1 ── * Track * ── 1 Genre
                                  * ── 1 MediaType
                                  * ── * Playlist       via PlaylistTrack

Employee 1 ── * Customer 1 ── * Invoice 1 ── * InvoiceLine * ── 1 Track
    │
    └── self-reference via ReportsTo
```

## Tables and grain

| Table | Rows | Grain and useful fields |
| --- | ---: | --- |
| `Artist` | 275 | One artist. PK `ArtistId`; display `Name`. |
| `Album` | 347 | One album. PK `AlbumId`; title; FK `ArtistId`. |
| `Track` | 3,503 | One catalog item. PK `TrackId`; album, genre, media type, composer, duration, bytes, current price. |
| `Genre` | 25 | One genre. PK `GenreId`; name. |
| `MediaType` | 5 | One encoding or media type. PK `MediaTypeId`; name. |
| `Playlist` | 18 | One playlist. PK `PlaylistId`; non-unique name. |
| `PlaylistTrack` | 8,715 | Playlist-to-track membership. Composite PK (`PlaylistId`, `TrackId`). |
| `Customer` | 59 | One customer. PK `CustomerId`; identity, contact, location; FK `SupportRepId`. |
| `Employee` | 8 | One employee. PK `EmployeeId`; identity, title, dates; self-FK `ReportsTo`. |
| `Invoice` | 412 | One invoice. PK `InvoiceId`; customer, timestamp, billing-location snapshot, stored total. |
| `InvoiceLine` | 2,240 | One purchased track line. PK `InvoiceLineId`; invoice, track, historical price, quantity. |

Row counts are the audited counts for SHA-256 `7651ba378ac2fcd0dfc3c66fb101f7a7eed3ba39a612ec642b96e20702061f15`.

## Central-table columns

### `Invoice`

- Key and customer: `InvoiceId`, `CustomerId`
- Timestamp: `InvoiceDate`
- Billing snapshot: `BillingAddress`, `BillingCity`, `BillingState`, `BillingCountry`, `BillingPostalCode`
- Invoice-level amount: `Total`

Every audited customer has invoices. The stored total reconciles exactly, at two-decimal precision, to the sum of its invoice lines.

### `InvoiceLine`

- Key: `InvoiceLineId`
- Relationships: `InvoiceId`, `TrackId`
- Measures: `UnitPrice`, `Quantity`

Use this table for artist-, album-, track-, genre-, or media-type-attributed sales. Its `UnitPrice` is the historical line price.

### `Track`

- Catalog hierarchy: `AlbumId`, `GenreId`, `MediaTypeId`
- Descriptive data: `Name`, `Composer`
- Measures: `Milliseconds`, `Bytes`, `UnitPrice`

All audited tracks have an album, genre, media type, positive duration, byte size, and nonnegative current price. `Composer` is missing for 977 tracks.

## Label and relationship caveats

- There are 199 duplicate track-name groups. Use `TrackId` and include album or artist context.
- There are 18 playlists but only 14 distinct names. `Music`, `Movies`, `TV Shows`, and `Audiobooks` each occur twice.
- Both `Music` playlists contain the same 3,290 tracks; both `TV Shows` playlists contain the same 213 tracks. All four `Movies` and `Audiobooks` playlist rows are empty.
- Every track belongs to at least two playlists, and some belong to five. Playlist-based totals overlap and are not additive.
- Seventy-one artists have no albums. Use a left join when measuring catalog coverage rather than sales activity.
- Customer `Company` is null for 49 of 59 customers. Use `CustomerId` and customer name for customer analysis.

## SQLite-specific details

- `InvoiceDate`, employee dates, and other declared `DATETIME` fields use text storage.
- There are no views or triggers.
- Eleven explicit non-unique indexes cover foreign-key columns; the composite playlist membership primary key has an automatic unique index.
- Foreign keys are declared and currently valid, but enforcement is disabled by default for a new SQLite connection.
- The schema has no `CHECK` constraints for positive quantities, prices, totals, durations, or byte counts. The audited rows are valid, but authorized writes need application-side validation.
