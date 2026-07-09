---
name: LivingStay Claude-zip 선택 병합 전략
description: 외부에서 받는 livingstay_vN zip을 병합할 때 매번 되돌려지는 우리 수정들 — 유지 목록
---

# 규칙
새 `livingstay_vN_*.zip`을 받아 병합할 때, 그 zip은 **매번 우리가 이미 고쳐둔 것들을 되돌리려 한다.** 아래는 항상 우리 버전을 유지(keep)하고 zip의 되돌림을 거부할 항목:

- **env 읽기**: `os.environ.get(KEY, "")` 유지. zip은 `os.environ[KEY]`(하드 실패)로 바꾸려 함.
- **JUSO 괄호/꼬리표 제거**: `road_to_jibun`에서 `keyword = road_address.split(",")[0]` + 끝 `(법정동)` 괄호 정규식 제거 유지. zip은 원문 그대로 넘김.
- **/api/health**: ISO 날짜(`isoformat(timespec="minutes")`) + `total_transactions` 유지. zip은 RFC 날짜 + `rows_inserted`로 되돌림.
- **/api/favorites**: 미매칭 거래 `building_name IS NULL` 매칭(프론트 favKey가 "null" 문자열로 저장됨) 유지. zip은 단순 `= %s`로 되돌림.
- **verify_units**: 청크/증분 구조 유지.
- **static/index.html**: 우리 버전이 항상 더 앞섬 — 숫자 헤더 우측정렬(`th.num`), 관심단지 칩 이름 클릭(showFav) + 안전 DOM(innerHTML XSS 아님). zip은 innerHTML 문자열 + `rows_inserted`로 되돌림. → index.html은 zip에서 가져오지 말 것.
- **raw_key = base_key|발생순번**: `base_key = sgg_cd|_norm_umd(umd)|jibun|deal_date|price|floor_val`, `raw_key = base_key|occurrence#`. `occurrence_counter` dict는 `(sgg_cd, deal_ymd)` fetch마다 초기화하고 skip 이전에 **모든 거래**를 센다. sync_batch·discover **둘 다 반드시 `_norm_umd(umd)`(공백제거)** 사용 — 한쪽이 원본 umd 쓰면 면/리 지역서 같은 거래가 다른 raw_key로 중복됨(architect가 지적). floor는 `t.get("floor") or t.get("flrNo")` 폴백. zip은 이 키를 단순 `sgg_cd|umd|jibun|date|price`로 되돌리려 함 → 같은 날·가격 다중 호실이 1건으로 뭉개짐(예: 수원 엠제이스톤 국토부 4건→1건).

**Why:** v6·v7 두 번 연속 같은 되돌림이 반복됨. 매 병합마다 diff 전체를 보고 위 항목을 지켜야 함.
**How to apply:** zip 병합 시 `diff -u` 로 파일별 비교 후, 위 목록은 우리 것 유지하고 zip의 **새 기능만** 취사선택.

# umd_nm 저장 형식 비대칭 — 교차 매칭 시 반드시 양쪽 공백제거
`transactions.umd_nm`은 RTMS 원본대로 **공백 포함**("봉평면 면온리", 전체의 ~2/3가 공백 있음), `master_buildings.umd_nm`은 **공백 없음**("봉평면면온리")으로 저장된다. 그래서 두 테이블을 잇는 모든 쿼리는 `REPLACE(umd_nm,' ','')` 로 양쪽을 정규화해 비교해야 한다(예: 용도 정정 API가 master 조회·transactions UPDATE 할 때). 단순 `umd_nm=%s` 정확일치는 면/리 지역에서 조용히 매칭 실패("마스터에서 찾지 못함")한다.
사용자 제출 건물을 신마스터에 넣을 때도 `umd_nm=(emdNm+liNm).replace(" ","")` 로 저장해야 이후 sync 매칭에서 누락 안 됨. zip은 이걸 `emdNm`만으로 되돌리려 함 → keep 우리 것.
**Why:** v3 병합 시 zip의 submit/correction이 정확일치를 써서 면/리 생숙이 전부 매칭 실패했음(architect 발견). 같은 종류 버그가 find_bjdong_cd·discover·sync·submit·correction 5곳에서 반복 재발했음.
**How to apply:** 동이름 정규화는 **address_utils.normalize_umd_nm() 하나만** 쓴다(`"".join(split())`). sync_batch·discover는 `_norm_umd = normalize_umd_nm` 별칭. 로컬에 `.replace(" ","")`나 자체 _norm_umd 재정의 금지 — zip이 자꾸 로컬 def를 되살리므로 병합마다 확인. 신규 SQL에서 두 테이블 umd 비교 시 `REPLACE(umd_nm,' ','')` 사용.

# init_db 부팅 호출
`app.py`가 import 시 `init_db()`를 호출한다(멱등: CREATE/ALTER IF NOT EXISTS). 이렇게 안 하면 building_requests 같은 신규 컬럼이 sync 스크립트가 처음 돌기 전까지 없어서 배포 직후 요청 API가 500 남. zip은 이 호출을 안 넣음.

# BjdongMap (법정동코드) — v7에서 전면 재작성됨(이건 적용)
실제 `법정동코드_전체자료` 파일은 **CSV 아님**: 탭 구분 `.txt`, 컬럼 3개(`법정동코드`/`법정동명`/`폐지여부`), cp949. `법정동명`은 시도+시군구+읍면동이 공백 하나로 합쳐진 단일 컬럼. zip 그대로여도 `BjdongMap._resolve_path`가 자동 압축해제. `all_sgg_codes()`가 전국 최말단 시군구(구 있으면 구 단위)만 골라냄 → `discover_new_buildings.py --list-only` 기대값 **256개**.
`BJDONG_CODE_CSV` 환경변수에 이 파일(zip 가능) 경로 지정. 파일이 첨부에서 자주 누락되므로 병합 전 존재 확인 필수.
