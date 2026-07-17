---
name: prod map shows 0 buildings (dev fine)
description: diagnosing "(0개 건물)" / empty map on production while dev works — usually prod DB coordinates, not a frontend/mobile bug
---

When the map legend reads "(0개 건물)" or markers are empty **only when tested on a phone**, suspect prod-vs-dev DB, not mobile CSS.

**Why:** The user opens the app on their phone via the published URL (livingstay-realtrade.replit.app), which runs on a **separate production database**, while the desktop dev preview uses the dev DB. So a "mobile-only" report can actually be a production-wide data problem affecting every device.

**How to apply:**
- `/api/buildings-geo` filters `WHERE lat IS NOT NULL AND lng IS NOT NULL`. If prod `master_buildings` rows exist but their lat/lng are all NULL (coordinates never populated in prod), the endpoint returns 0 → empty map on prod only.
- Quick check: `curl https://<prod-domain>/api/buildings-geo` vs dev; and `executeSql({environment:"production"})` counting `master_buildings WHERE lat IS NOT NULL`.
- The `#mapCount` span starts empty in HTML; "(0개 건물)" being shown means JS ran `loadMapMarkers` to completion with 0 placed — i.e. the API genuinely returned 0, not "JS failed to load".
- Fix path is data-side (populate prod coordinates / sync), governed by Replit's publish-time flow — not a frontend change.

**Fix mechanism (how prod coords actually get filled):** the agent CANNOT write prod (executeSql production = read-only replica; `UPDATE` → "production environment is read-only"). Only the deployed app writes the real prod DB. So the pattern is: export dev coords to a committed data file (`data/building_coords.json`, list of {id,lat,lng}), and an admin-only endpoint `POST /api/admin/geocode` (+ `GET /api/admin/geocode/status`) that the deployed app runs to `UPDATE master_buildings` by id. Idempotent guard `AND (m.lat IS DISTINCT FROM v.lat OR m.lng IS DISTINCT FROM v.lng)` → re-run reports 0. Last-run summary stored in `app_meta` (key-value table in db.py init_db). Admin UI: sidebar `data-menu="geocode"` → `showGeocode()`. Requires user to Push + Publish, then click the button once on the live admin.
**Note:** live UPDATE tests in dev time out while `Fast Sync`/`Backfill Retry` workflows hold locks on master_buildings — that's lock contention, not a code bug.

**Same pattern for 표제부(건축정보) fields:** dev backfill (`backfill_title_info.py`) fills use_apr_day/grnd_flr_cnt/tot_area/... in DEV only; prod stays NULL (checked 2026-07-17: prod backfilled=0/474 while dev=473/476), so the deployed B-screen shows "-" for EVERY building. A single-building "-" report on the phone is really prod-wide. Fix path = same admin-endpoint data-sync pattern as coords, not a re-run of the backfill.
