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
  `sgg_nm` = `sgg_text LIKE '%sgg_nm%'`, `umd_nm` = `REPLACE(umd_nm,' ','') ILIKE '%...%'`,
  and for `si_do` use the suffix-stripped core-name equality below (NOT a prefix).

- **`si_do` notation varies on BOTH sides, so prefix matching silently drops rows.**
  `transactions.si_do` has both `"서울"` (10) and `"서울특별시"` (623);
  `master_buildings.sgg_text` has both `"서울 강남구"` (2) and `"서울특별시 …"` (38).
  A `LIKE '서울특별시%'` filter (the common dropdown pick) MISSES the 2 `"서울 강남구"`
  buildings. **Fix (in use):** strip the admin suffix from both sides and compare
  cores for equality — `re.sub(r"(특별자치도|특별자치시|특별시|광역시|도|시)$","",si_do)`
  vs `regexp_replace(split_part(sgg_text,' ',1),'(…same…)$','')`. Both "서울" and
  "서울특별시" then resolve to core "서울" → all 40 Seoul buildings.
  **Why:** upstream RTMS data inconsistency; longest-suffix-first order avoids
  wrongly stripping "시"/"도" from names like "서울특별시".

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
