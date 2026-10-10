# 온비드 공매 수집·연결·업무 흐름

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 출처·전송
- CONFIRMED 온비드 공공 API B010003 계열; URL은 external_api_inventory.csv. `sync_onbid.py` → `public_api_get(...purpose="batch",timeout=(15,30))` → 조건부 RELAY_USE_ONBID.
- `sync_onbid.py:46` · `_onbid_get()`: RELAY_QUOTA는 BudgetExceeded, RELAY_AUTH/FORBIDDEN은 PermissionError, 그 외 RelayError는 execution failure. direct 우회 없음 (switch OFF는 원래 direct).
- `sync_onbid.py:130` · `reserve()`: API 요청 전 DB 예산 예약. claim/own/heartbeat/run_id에 따른 배치 소유권; list→detail·작은 commit·checkpoint.

## 데이터·좌표·연결
| asset | rows | linked_buildings |
| --- | --- | --- |
| auction_items | 8883 | 598 |

auction_items는 source/source_item_id/pbct_cdtn_no/가격/기간/status/usage/좌표/master ID/raw/detail_fingerprint와 확인 항목을 보유. 회차 auction_rounds·사진 auction_photos·관심 auction_watches는 별도 테이블. source+item 같은 물건과 회차를 혼동하지 않습니다. `auction_building_matching.py`/`auction_building_enrichment.py`의 주소·지번·대장 증거로 연결; 미연결도 공매 자체 및 조사 신청과 분리합니다.

## 화면·관리
`auction_service.py.register_auction_routes` → 목록/상세/관심/건물별 공매. `main.js` 지도 공매 overlay, 공개 숙박 총계에 공매 물건 수를 더하지 않는 별도 표시. `survey_service.py`·survey_requests·membership_checks는 현황조사/멤버십 업무 경로. 법원경매 자동조회·중개/입찰대행·최종 낙찰 결과는 온비드 metadata만으로 보장되지 않습니다. 기존 공매 상세 3탭과 status 이력은 보존 대상입니다.

## 실행 상태
워크플로/관리자 수동 수집 경로는 확인했으나 이번 작업에서는 어떤 수집도 시작·정지·재시작하지 않았습니다. YES24 및 upstream 실제 응답/이미지/최근 공매 갱신 상태는 UNKNOWN입니다.
