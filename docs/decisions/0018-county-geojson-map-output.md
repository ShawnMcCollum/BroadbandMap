# 0018 — County GeoJSON for initial map output

- **Status:** Accepted
- **Date:** 2026-10-16

## Context

Issue #3 must expose map-ready output alongside Served/Not served summaries.
The first map is Ohio by county. TIGER/Line 2020 polygons are already stored in
PostGIS in WGS84. React needs geometry and counts; the analyst dashboard needs
counts without large polygons. A format choice should address actual county
payloads before adding infrastructure for finer geographic levels.

A read-only profile of the downloaded Ohio county shapefile found 88 counties
and 122,526 coordinate vertices. At six decimal places, compact polygon geometry
alone was approximately 2.79 MB, with the largest county approximately 97.6 KB.
This estimate informed the choice; the implemented endpoint retains coordinate
precision and is measured separately against the loaded database.

The implemented endpoint returns all 88 counties in 3,344,412 bytes, including
feature properties and pagination metadata, below the 5 MiB cap. The matching
county summary JSON is 12,251 bytes. These local measurements support separating
the two representations and retaining the unsimplified county polygons.

## Decision

- Expose county boundaries through
  `GET /api/v1/geographies/county/?state=39`, separately from summary JSON.
- Use RFC 7946 FeatureCollection/Feature structures and `application/geo+json`.
  County GEOIDs are string feature IDs and properties, matching summary `code`.
- Return MultiPolygons with WGS84 longitude/latitude coordinates. Force exterior
  rings counterclockwise and interior rings clockwise in PostgreSQL. Serialize
  with 15 decimal places of precision; do not simplify or intentionally round
  coordinates for display. Do not emit a legacy `crs` member.
- Require an explicit state and paginate deterministically by county code.
  Default and maximum page size are 100 features. Cap the rendered response at
  5 MiB, checking geometry size in PostgreSQL before transferring polygons and
  checking the final response including metadata and negotiated indentation.
  Over-cap requests receive a structured 400 and advice to request fewer features.
- Boundaries have vintage 2020 and do not claim release coverage or availability.
  Clients join summary codes to geometry IDs. Missing summaries remain unclassified.
- Return `Cache-Control: no-store` initially, consistently with the API conventions.

## Alternatives

- **Vector tiles:** useful for viewport-dependent, high-volume geometry. Defer
  until finer levels or larger map areas justify tile generation, serving, and
  a second representation contract through measurements.
- **Polygons embedded in each summary:** repeats geometry for flag/date changes
  and burdens table consumers. Separate resource contracts avoid that cost.
- **Simplifying or reducing coordinate precision:** could reduce bytes, but
  requires a display tolerance and topology review. The county payload does not
  justify that extra policy in the initial implementation.

## Consequences

Both clients share summary identifiers without requiring a tile service or a
new dependency. Feature and byte limits bound reads even as additional states
are loaded. States with many counties may need several pages. A single polygon
that exceeds the byte cap remains unavailable through this representation;
smaller page sizes cannot resolve that case, and a future representation decision
would be needed. Page-number reads do not promise a snapshot across requests.

References: [RFC 7946](https://www.rfc-editor.org/rfc/rfc7946.html),
[GeoDjango database functions](https://docs.djangoproject.com/en/5.2/ref/contrib/gis/functions/),
[ADR 0016](0016-rest-api-contract-and-tests.md),
[ADR 0017](0017-national-releases-loaded-by-state.md).
