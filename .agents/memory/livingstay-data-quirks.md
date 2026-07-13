---
name: livingstay data/schema quirks
description: Non-obvious data facts for the livingstay 생숙 app — table shapes and dirty region values you can only learn by querying the DB.
---

# livingstay 데이터/스키마 quirks

Facts you can only discover by querying Postgres, not by reading code.

- **`master_buildings` (지도 마커의 출처) has NO `si_do`/`sgg_nm` columns.** It has
  `sgg_text` (e.g. `"서울특별시 서초구"`, `"강원특별자치도 홍천군"`) and `umd_nm`.
  `transactions` (게시판의 출처) has separate `si_do` / `sgg_nm` / `umd_nm`.
  **Why:** the two tables were populated from different sources; any feature that
  filters BOTH the map and the board by region must bridge this shape mismatch.
  **How to apply:** to filter the map by the board's region params →
  `si_do` = `sgg_text LIKE 'si_do%'` (prefix), `sgg_nm` = `sgg_text LIKE '%sgg_nm%'`,
  `umd_nm` = `REPLACE(umd_nm,' ','') ILIKE '%...%'`.

- **`transactions.si_do` is dirty: both `"서울"` AND `"서울특별시"` exist** as
  distinct values (region dropdown from /api/regions therefore shows both).
  Prefix-matching `sgg_text LIKE '서울%'` absorbs both on the map, but the board
  uses exact `si_do =`, so map vs board counts under 서울 can differ slightly.
  **Why:** upstream RTMS data inconsistency, not a bug in our code.

- **`umd_nm` spacing differs between the two tables**: transactions store
  `"손양면 동호리"` (space) while master stores `"손양면동호리"` (no space).
  Strip spaces on both sides before comparing.

- **`lodging_type` values** (both tables): `생활`, `호텔`, `콘도`, plus 복합 forms
  like `생활·호텔`, `호텔·콘도`. UI/backend convention: dropdown value `복합`
  → SQL `lodging_type LIKE '%·%'`; any other value → exact `=` match (so `생활`
  does NOT include `생활·호텔`). Keep map and board using the identical rule.

- Rough counts (2026-07): 476 buildings have lat/lng; 서울 prefix ≈ 40,
  강원특별자치도 ≈ 101, 콘도 = 6, 복합 = 12. Useful as a sanity check when
  verifying map filters.
