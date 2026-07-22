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

**Fix mechanism (how prod coords/표제부 get filled):** the agent CANNOT write prod (executeSql production = read-only replica). Only the deployed app writes the real prod DB. (2026-07-22) The old committed-JSON injection (`data/building_coords.json`/`building_title_info.json` + idempotent UPDATE endpoints) was REPLACED by live-API detached runners on the admin "데이터 동기화" page: `POST /api/admin/geocode-buildings` runs `geocode_buildings.py --status-key geocode_sync_status` (Kakao geocoding of lat-NULL buildings) and `POST /api/admin/backfill-title-info` runs `backfill_title_info.py --status-key title_info_sync_status` (건축HUB 표제부, title_backfilled_at NULL only) — same lock/heartbeat/run_id pattern as tx sync. So the prod fix is: publish, then click the buttons on the live admin (no JSON export step anymore).
**Note:** live UPDATE tests in dev time out while `Fast Sync`/`Backfill Retry` workflows hold locks on master_buildings — that's lock contention, not a code bug.
**Note:** 건축HUB 표제부 shares the daily quota with `BRHUB Sync` — if the bulk scan burnt the quota, the 건축정보 button ends "done" with all-ERR (429); retry next day.
