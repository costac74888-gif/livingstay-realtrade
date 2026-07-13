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

- **`si_do` notation varies on BOTH sides, so any region filter must normalize.**
  `transactions.si_do` has both `"서울"` (10) and `"서울특별시"` (623);
  `master_buildings.sgg_text` has both `"서울 강남구"` (2) and `"서울특별시 …"` (38).
  A prefix `LIKE '서울특별시%'` filter (the common dropdown pick) MISSES the 2
  `"서울 강남구"` buildings, and an exact `si_do =` on the board splits Seoul 623/10.
  **Fix (in use):** ONE shared pair in `address_utils.py` — `sido_core(si_do)`
  strips the admin suffix, `sido_match_clause(col_expr)` returns the matching SQL
  (`regexp_replace(col, SIDO_SUFFIX_RE, '') = %s`). BOTH `/api/buildings-geo`
  (col = `split_part(sgg_text,' ',1)`) and `/api/transactions` (col = `si_do`)
  call this pair, so "서울"/"서울특별시" both resolve to core "서울".
  **Why:** upstream RTMS inconsistency; the two endpoints used to diverge (prefix
  vs exact), so keep them on the shared helper — never re-add per-endpoint si_do
  logic. Longest-suffix-first order avoids wrongly stripping "시"/"도".
  **Verified totals:** map 서울=40; board 서울="서울특별시"=633 (=623+10).

- **`umd_nm` spacing differs between the two tables**: transactions store
  `"손양면 동호리"` (space) while master stores `"손양면동호리"` (no space).
  Strip spaces on both sides before comparing (`REPLACE(umd_nm,' ','')`).
  **Safety-critical:** any query that attributes transactions to a master building
  by jibun-key (`sgg_cd`+`umd_nm`+`jibun`) MUST normalize umd_nm, or it undercounts.
  For a delete/reference guard this is a data-integrity bug — an exact-match guard
  returns 0 for a spaced variant and lets you orphan real 실거래 (verified: spaced
  을지로5가/77-2/11140 → exact match=0 but normalized=11). Guards should over-match.

- **`lodging_type` values** (both tables): `생활`, `호텔`, `콘도`, plus 복합 forms
  like `생활·호텔`, `호텔·콘도`. UI/backend convention: dropdown value `복합`
  → SQL `lodging_type LIKE '%·%'`; any other value → exact `=` match (so `생활`
  does NOT include `생활·호텔`). Keep map and board using the identical rule.

- **One `(sgg_cd, umd_nm, jibun)` parcel can hold MANY distinct master buildings.**
  Resort/condo complexes (동/호 units) and name-variant duplicates share a jibun
  (e.g. 스카이썬 / 스카이썬(이든프롭스); 본재 / 파르마 스테이). Matching latest
  transaction by jibun ALONE cross-contaminates (one 필지's tx spreads to all its
  buildings) — 7 parcels w/ tx = 16 buildings; 17 dup groups = 44 buildings total.
  **Fix (in use):** `/api/buildings-geo` LATERAL keeps the jibun WHERE but ranks
  `ORDER BY (t.building_name = mb.building_name) DESC NULLS LAST, t.deal_date DESC`
  → exact-name tx first, else the parcel's latest as a reference. Response exposes
  `latest_price_exact` (COALESCE(...,FALSE)); FALSE = same-parcel 참고가, shown in
  UI as "(필지 내 참고가)" on hover tooltip + label + InfoWindow (all render from
  the same latest_* payload). **Why:** jibun is NOT a unique building key here;
  true disambiguation would need 동/호 or a building id we don't have.

- **data.go.kr 숙박업 API (15155124, `apis.data.go.kr/1741000/lodgings/info`) 지역 필터
  = `cond[OPN_ATMY_GRP_CD::EQ]` (개방자치단체코드).** 코드 단위는 **기초자치단체(시/군/구)**,
  총 261개 = 시/도전체 `_ALL` 17개 + 개별 244개. 광역시 자치구·군은 각각 별도 코드지만,
  **도 산하 큰 시의 일반구(행정구)는 시 코드 하나로 통합**(예: 안양시 3830000이 만안/동안 포함,
  응답 MNG_NO 앞자리로만 구가 갈림). **3830000 = 경기안양시 (평택 아님!); 평택시 = 3910000.**
  업태 구분 필드 = `BZSTAT_SE_NM`(생활숙박업 값 = `"숙박업(생활)"`) — 요청 필터 없음, client-side.
  영업상태 = `cond[SALS_STTS_CD::EQ]` (01영업/02휴업/03폐업/04취소·말소/05제외·전출/06기타).
  참고문서 xlsx 다운로드: `/cmm/cmm/fileDownload.do?atchFileId=<FILE_id>&fileDetailSn=1`
  (FILE_id는 상세페이지 `fn_fileDownload(...)` 호출에서 추출). serviceKey는 RTMS와 동일 키를 params로 전달.

- Rough counts (2026-07): 476 buildings have lat/lng; 서울 prefix ≈ 40,
  강원특별자치도 ≈ 101, 콘도 = 6, 복합 = 12. Useful as a sanity check when
  verifying map filters.

## 지자체 담당부서(담당부처/연락처) 매칭 — 애매하면 반드시 null
- 출처: 사용자가 올린 엑셀(지자체/담당부서/전화번호 ~135행) → `lodging_authority_contacts`에 원본 그대로 적재(TRUNCATE+INSERT). 전화번호가 `"-"`인 행도 있으니 원본 그대로 표시.
- master `sgg_text`(공백구분 `"{시도} {시군구} [{구}]"`)를 엑셀 지자체명(붙여쓰기/시도생략 혼재)과 매칭. `address_utils.py`의 `build_authority_index`+`match_authority_contact`가 우선순위 (a)`(sido,local)` 정확 → (b)시도생략행 → (c)시도 대표 fallback.
- **결정: 후보가 복수이고 값이 상충하면 추측하지 말고 `ambiguous`→null(화면 "확인중").** 동일값은 set으로 자동 병합(진주시 중복 OK), 상충(대전 중구 등)은 차단.
  **Why:** 데이터 정확성이 중요한 서비스 — 잘못된 관공서 연락처 노출은 오매칭 중 최악. 매칭률보다 오매칭 0을 우선한다.
  **How to apply:** source 값은 'exact'/'fallback'만 화면 표시(fallback이면 부서명 뒤 "(시/도 대표)" 회색 꼬리표), 그 외(no_master/no_match/ambiguous)는 dept=phone=None. 광주(경기광주시 vs 광주광역시)는 시도 분기로 안 섞임 — 새 지역 추가 시 이 케이스 회귀 확인.
- 인덱스는 `app.py` 모듈 캐시(`_AUTHORITY_INDEX` lazy). 엑셀 재적재 후에는 **앱 재시작**해야 반영(gunicorn 자동 리로드 없음).

## /api/transactions size 상한 200
- `/api/transactions`는 요청당 `size = min(size, 200)`으로 상한이 걸려 있다. "더보기"류로 size를 계속 키우는 방식은 200건 초과 건물에서 무한 루프(버튼이 계속 남고 더 안 불러옴)가 된다.
- **적용:** 건물 상세 실거래목록처럼 누적 표시가 필요하면 200건씩 페이지를 이어 받아 합산 후 slice 하라. 관심단지 전용 조회는 별도 엔드포인트(size 상한 무관)가 이미 존재.
