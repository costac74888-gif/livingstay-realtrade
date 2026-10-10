# 국토부 실거래 데이터

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 수집/중계/저장
- RTMS_SERVICE_KEY → `sync_batch.py` 및 `sync_rural_hanok_trades.py`/관련 app 호출; `public_api_get`의 rtms bucket으로 조건부 relay. NrgTrade/RHTrade/SHTrade/LandTrade 서비스 prefix를 허용.
- `sync_batch.py:277` · `fetch_nrg_trade()`: 업무·상업용 중심 기존 조회; `sync_rural_hanok_trades.py`는 토지/단독/연립 등 scope를 구분하는 추가 경로.
- `transactions`: raw_key·deal_date·deal_type·price·area·sgg_cd·umd_nm·jibun·주소·건물명·source_api·source_building_type·transaction_scope·match_confidence·master_building_id 보유. 가격 단위는 API parsing/화면 변환을 그대로 따라야 하며 매물 field 이름만으로 KRW 원 단위라고 가정하면 안 됩니다. 현재 listing_requests.price_krw는 레거시 이름과 달리 만원 단위로 처리합니다(app.py:13082,13118; main.js:7279). 온비드 price_minimum_krw 등 실제 원 단위와의 혼합이 별도 위험입니다.
- raw_key 관련 UNIQUE/중복방지는 schema 인덱스와 ON CONFLICT 경로로 확인; `sync_failures`·quota/checkpoint·월별 재처리·run_id fence 등의 collector 체계를 보존해야 합니다.

## 건물 연결
`sync_batch.py:312` · `transaction_scope_for_trade()`; `sync_batch.py:317` · `whole_building_match_reason()`; `sync_batch.py:341` · `exact_master_for_unit_trade()`.
일반 건물 거래는 whole_building, 그 외는 unit 분기. 전체 건물 자동연결은 정확히 한 일반숙박 master 조건, 호실은 유일 후보 또는 정확한 원천 건물명 대조를 사용. 시군구/읍면동/지번·도로명 정규화가 연결에 관여하고 ambiguous는 임의 연결하지 않습니다. 토지 거래는 건물 거래와 합치지 않습니다.

## 운영 규모 (CONFIRMED COUNT)
| asset | rows | linked_buildings |
| --- | --- | --- |
| transactions | 19094 | 1283 |

여기 연결 건수는 master_building_id가 NULL이 아닌 거래 행 수이며 서로 다른 건물 수가 아닙니다. 주소/이름 기반 조회 후보는 이 계수에 포함되지 않습니다.

## 노출·분석·관리
`app.py` 거래 API/랭킹/건물 상세, `main.js` 실거래 표시, 자산분석은 최신·유일 매칭·범위 조건의 거래 기준치를 사용합니다. `sync_runner.py`/`scheduled_sync.py` 및 관리자 수동 collector가 존재합니다. 실제 신규 수집·사용자 API·관리자 버튼은 실행하지 않았습니다. DataLab 및 투자/운영 추이의 모든 화면별 숫자 재현은 UNKNOWN이며 static route/함수 근거는 routes.csv에 포함됩니다.
