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

**Why:** v6·v7 두 번 연속 같은 되돌림이 반복됨. 매 병합마다 diff 전체를 보고 위 항목을 지켜야 함.
**How to apply:** zip 병합 시 `diff -u` 로 파일별 비교 후, 위 목록은 우리 것 유지하고 zip의 **새 기능만** 취사선택.

# BjdongMap (법정동코드) — v7에서 전면 재작성됨(이건 적용)
실제 `법정동코드_전체자료` 파일은 **CSV 아님**: 탭 구분 `.txt`, 컬럼 3개(`법정동코드`/`법정동명`/`폐지여부`), cp949. `법정동명`은 시도+시군구+읍면동이 공백 하나로 합쳐진 단일 컬럼. zip 그대로여도 `BjdongMap._resolve_path`가 자동 압축해제. `all_sgg_codes()`가 전국 최말단 시군구(구 있으면 구 단위)만 골라냄 → `discover_new_buildings.py --list-only` 기대값 **256개**.
`BJDONG_CODE_CSV` 환경변수에 이 파일(zip 가능) 경로 지정. 파일이 첨부에서 자주 누락되므로 병합 전 존재 확인 필수.
