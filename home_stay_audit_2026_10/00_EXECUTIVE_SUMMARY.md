# HOME & STAY 2.0 — 0단계 조사 요약

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 조사 범위 및 수량
| 항목 | 수량 |
| --- | --- |
| code_files | 433 |
| db_tables | 135 |
| db_columns | 1625 |
| route_method_pairs | 616 |
| distinct_route_paths | 546 |
| external_api_sdk_url_candidates | 58 |
| external_api_endpoints_static | 39 |
| environment_usage_sites_application_config | 339 |
| environment_usage_sites_all | 740 |
| environment_names_referenced | 106 |
| master_direct_fk_constraints | 38 |
| master_direct_fk_tables | 37 |
| admin_menus | 32 |
| major_risks | 20 |

- CONFIRMED: 운영 건물마스터 **85,617건**, 좌표 보유 **85,013건**. 숙박 신고 원장 **145,631행**. 집계는 조회 시점이며 서비스 대표 총계와 같다고 보장하지 않습니다.
- CONFIRMED: 서비스는 `https://homenstay.com`, `autoscale` 배포. 이번 조사에서 HTTP 방문/배포하지 않았습니다.
- CONFIRMED: 모든 운영 관계를 `master_buildings.id` 중심으로 공유하고, 법정 영업분류와 건축물 용도를 별도 필드로 보유합니다.
- CONFIRMED: Relay는 4개 계열(bldg_hub/rtms/onbid/juso)의 옵션 전송 계층이며 파서·재시도·쿼터는 수집기 소관입니다. UNKNOWN: YES24 서버의 실제 배포 코드·실행 스위치 값·quota·TLS.
- INFERRED: 신규 단기임대를 모든 건축물 용도에 개방하는 것은 별도 등록 자산/매물/지도 레이어로 확장하면 가능성이 있습니다. 기존 숙박 원장 재구축으로 대체하는 방식은 부적합합니다.
- UNKNOWN: 신규 예약·캘린더·재고·취소·환불·정산·법적 운영 정책의 완성 여부. 이름만 비슷한 현재 테이블로 완성됐다고 판단하지 않았습니다.

## 산출물 사용법
19개 상세 Markdown, 7개 필수 CSV, 추가 schema/파일 CSV, 통합 Markdown을 제공합니다. `02_ROUTE_API_INVENTORY.md`와 `routes.csv`의 AUTH/DB/외부API 후보는 정적 조사 범위를 표시합니다. 인증 guard가 보인다고 항상 인증 필수인 것은 아닙니다. `03_DATABASE_SCHEMA.md`에 전체 컬럼·제약·인덱스·sequence가 포함됩니다.

## 금지 작업 준수
보고서 작성 이외의 변경·실행은 없음. 개편 제안은 분석 의견이며 구현하지 않았습니다. 기존 수집기의 자율 실행을 중단하거나 조정하지 않았습니다.

외부 API 수는 API/OAuth/WMS endpoint의 고유 정적 URL 기준이며 provider 수/실제 호출 횟수와 다릅니다. base URL·웹링크·폰트는 분리했습니다. 환경 사용처 수는 직접 accessor와 동적 key/이름 참조를 포함하며 CSV에서 CONFIRMED/INFERRED 및 TEST를 구분합니다.
