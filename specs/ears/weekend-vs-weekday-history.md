# Weekend vs weekday price history

> A side-by-side bar chart comparing average hour-of-day NOK/kWh prices for weekdays and weekends over the two most recently completed Mon–Sun weeks, backed by a daily-refreshed in-memory cache.

**Type:** New feature
**System:** Backend (FastAPI) + Frontend (vanilla JS)
**Date:** 2026-05-21

## Context

The EV charge planner already shows today's NO1 spot prices and recommends a cheapest contiguous window. Users want to see whether weekend prices typically differ from weekday prices, to make better routine decisions (e.g. "charge Sunday morning"). The data source is the same `hvakosterstrommen.no` API used elsewhere, but fetching 14 days on every page load is wasteful — so the result is cached in process memory and refreshed once per Europe/Oslo calendar day on the first request of that day.

## Pending changes

- [ ] **REQ-001** — Expose `GET /api/prices/history`.
- [ ] **REQ-002** — Return a 24-entry weekday + weekend profile JSON.
- [ ] **REQ-003** — Fetch 14 days from upstream on cache miss.
- [ ] **REQ-004** — Store computed profile in in-memory cache keyed by Oslo date.
- [ ] **REQ-005** — Serve cached profile without upstream call when fresh.
- [ ] **REQ-006** — Single-flight concurrent requests during in-flight fetch.
- [ ] **REQ-007** — Frontend issues one history request on page load.
- [ ] **REQ-008** — Frontend renders 24-position grouped bar chart.
- [ ] **REQ-009** — Frontend renders chart legend.
- [ ] **REQ-010** — Backend excludes 404 days from averages.
- [ ] **REQ-011** — Backend lists excluded ISO dates in `missing_days`.
- [ ] **REQ-012** — Backend returns 503 when all 14 days missing.
- [ ] **REQ-013** — Backend returns 502 on non-404 upstream errors.
- [ ] **REQ-014** — Frontend shows warning when `missing_days` is non-empty.
- [ ] **REQ-015** — Frontend shows error message on non-200 response.
- [ ] **REQ-016** — Two-week window definition (Mon of 2nd-most-recent week → Sun of most-recent complete week, Oslo).
- [ ] **REQ-017** — Weekday/weekend classification by Oslo calendar date.
- [ ] **REQ-018** — NO1 only.
- [ ] **REQ-019** — Cache held in process memory only.
- [ ] **REQ-020** — Cache not written when an upstream fetch fails.

## Requirements

### Functional requirements

REQ-001: The backend shall expose `GET /api/prices/history` returning the weekday-vs-weekend hour-of-day price profile for NO1 over the two most recently completed Monday–Sunday weeks.

REQ-002: When `GET /api/prices/history` is requested, the backend shall respond with a JSON body containing two arrays of 24 entries each — `weekday` and `weekend` — where every entry holds the hour-of-day (0–23), the average NOK/kWh for that hour across the contributing days in the window, and the count of contributing days.

REQ-003: When `GET /api/prices/history` is requested and the in-memory cache holds no profile keyed by the current Europe/Oslo calendar date, the backend shall fetch hourly NO1 prices for each of the 14 target days from `hvakosterstrommen.no`.

REQ-004: When the 14-day fetch completes successfully, the backend shall store the resulting profile in the in-memory cache keyed by the current Europe/Oslo calendar date.

REQ-005: When `GET /api/prices/history` is requested and the in-memory cache holds a profile keyed by the current Europe/Oslo calendar date, the backend shall return that cached profile without contacting `hvakosterstrommen.no`.

REQ-006: While a 14-day fetch for the history endpoint is already in progress, the backend shall cause every concurrent `GET /api/prices/history` request to wait for the in-flight fetch to complete and return its result.

REQ-007: When the frontend page loads, the frontend shall issue exactly one `GET /api/prices/history` request.

REQ-008: When the frontend receives a successful history payload, the frontend shall render a bar chart with 24 hour positions on the x-axis, two bars per position (weekday and weekend), and average NOK/kWh on the y-axis, in a dedicated "Weekend vs weekday" section beneath the existing EV planner section.

REQ-009: When the frontend renders the history chart, the frontend shall display a legend identifying the weekday and weekend series.

### Unwanted behavior / error handling

REQ-010: If `hvakosterstrommen.no` returns HTTP 404 for one or more of the 14 target days, then the backend shall exclude those days from the computed averages.

REQ-011: If any target days are excluded from the computed averages, then the backend shall list their ISO dates in a `missing_days` field in the response payload.

REQ-012: If `hvakosterstrommen.no` returns HTTP 404 for all 14 target days, then the backend shall respond with HTTP 503 and a JSON `{"detail": ...}` body explaining that no historical data is available.

REQ-013: If a call to `hvakosterstrommen.no` for the history endpoint fails with a non-404 error (timeout, 5xx, or network failure), then the backend shall respond with HTTP 502.

REQ-014: If the history payload contains a non-empty `missing_days` list, then the frontend shall display a warning above the chart that enumerates the missing ISO dates.

REQ-015: If `GET /api/prices/history` returns any non-200 status, then the frontend shall display an error message in the history section in place of the chart.

### Constraints

REQ-016: The backend shall compute the two-week window as the 14 consecutive calendar dates from the Monday of the second-most-recent complete ISO week through the Sunday of the most-recent complete ISO week, evaluated in Europe/Oslo.

REQ-017: The backend shall classify each day as `weekday` (Monday–Friday) or `weekend` (Saturday–Sunday) by its Europe/Oslo calendar date.

REQ-018: The backend shall fetch only NO1 prices for the history endpoint.

REQ-019: The backend shall hold the history cache in process memory only.

REQ-020: The backend shall not write the history cache when the 14-day fetch fails with any non-404 error.

## Verification notes

- **REQ-001..005, 010..013, 016..020:** unit-test the cache + window-computation logic with a fake clock and a mocked `httpx.get` (use `respx`, already a dev dep). Cover: cold cache, warm same-day cache, stale cache (different Oslo date), all-404, some-404, network error.
- **REQ-006:** integration test that fires two concurrent `httpx.AsyncClient` requests against an `app` whose underlying HTTP layer is mocked to block; assert only one upstream call.
- **REQ-007..009, 014..015:** open the page in a browser; with DevTools Network panel confirm a single `/api/prices/history` request; visually confirm 24 grouped pairs of bars, legend, and warning/error rendering when the backend is forced to return 503/502.
- **REQ-016:** parametrize a unit test over several "today" dates (Mon, Wed, Sun) and verify the resulting 14-date range.

## Open questions

None identified.
