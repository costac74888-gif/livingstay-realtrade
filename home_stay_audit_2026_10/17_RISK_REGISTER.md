# 주요 위험 등록부

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

총 20개 위험. 기존 시스템 취약점이 실증됐다는 의미가 아니라, 확인된 의존성·미확인 영역에 대한 개편 위험입니다.

| id | priority | risk | evidence_status | evidence | analysis_only |
| --- | --- | --- | --- | --- | --- |
| R01 | CRITICAL | 기존 건물마스터를 전 건축물 원장으로 덮어쓰는 개편 | INFERRED impact; CONFIRMED dependency | master_buildings에 연결된 FK 및 기존 통계 분류 | 기존 원장·ID·sequence 보존; 신규 등록 건물 참조 계층은 별도 설계 의견만 제시 |
| R02 | CRITICAL | master_buildings 삭제/ID 재할당의 연쇄 영향 | CONFIRMED schema | ON DELETE CASCADE/SET NULL/RESTRICT 혼재, 다수 직접 FK | 삭제·재번호·sequence 초기화 금지; 링크 계보 유지 |
| R03 | HIGH | 숙박 영업분류와 건축물 용도 및 Airbnb 채널 혼동 | CONFIRMED code/data | lodging_classification.py; building_use_type; 운영에 생숙/기타/NULL 잔존 | 업종·용도·플랫폼 3개 의미를 분리; 데이터 재분류 금지 |
| R04 | HIGH | DB row count/공개 통계/관리자 통계의 불일치 오판 | CONFIRMED code | 분류 alias, 준공전 status, 주소매칭, distinct 신고, 별도 캐시 | 화면 수치를 원장 단순합으로 대체하지 않음; 각 산식 명시 |
| R05 | HIGH | 실거래 연결 범위·가격 단위 오판 | CONFIRMED code/data | transaction_scope; master_building_id; raw_key; 직접 ID 연결률·price_krw 레거시 만원 단위 | 호실/건물전체/토지 분리; 미연결 거래를 임의 연결 금지 |
| R06 | HIGH | 일반 카카오 전용 변경과 단일 계정 복수 역할 충돌 | CONFIRMED architecture; INFERRED change risk | users + role/business memberships; email/Kakao dual identity | 일반 화면 로그인 정책과 파트너 자격증명/역할 권한을 분리해 검토 |
| R07 | HIGH | 지도 참고 레이어가 기존 숙박 합계에 편입되는 위험 | CONFIRMED separate pipelines; INFERRED future risk | 관광 heatmap/공매/신규 단기임대 | 새 레이어와 기존 숙박 통계를 별도 집계 |
| R08 | HIGH | 제한공개 매물의 주소·좌표·건물정보 역추적 | CONFIRMED fields/guards; INFERRED regression risk | disclosure_scope; building_info_overrides; 지도 overlay | 신규 지도/주소검색에서 기존 익명화 계약을 유지 |
| R09 | HIGH | Relay 장애 시 우회 호출과 인증정보 로그 유출 | CONFIRMED fail-closed client; server UNKNOWN | public_api_client.py; secret_redaction.py | 클라이언트 fail-closed·오류 마스킹을 보존; 서버 실사는 별도 승인 필요 |
| R10 | HIGH | YES24 내부 allowlist/quota/TLS/서버 코드 미확인 | UNKNOWN | 현재 repo는 클라이언트이며 서버 접속/호출 없음 | 운영 서버 구성 증거 없이는 서버 보안/가용성을 확정하지 않음 |
| R11 | HIGH | 개발·운영 DB 선택 및 Publish DDL 영향 | CONFIRMED config; runtime DSN values UNKNOWN | DATABASE_URL/PROD_DATABASE_URL/DEV_DATABASE_URL; db.py init_db | 실제 DB 지문 확인과 schema diff 확인; 조사 단계 변경 금지 |
| R12 | HIGH | staging 승인 원본·manifest·legacy cutoff 손상 | CONFIRMED source modules | lodging_promotion/legacy_lodging_gate/quota_policy | 기존 원장·수동 검토 계보·중복 키·fence 정책 보존 |
| R13 | MEDIUM | 통계 캐시와 수집 중 집계의 시점 차이 | CONFIRMED code; work running | app_meta 신호; process cache; pooled DB priority | 집계 시각·캐시 세대 표시; 본 보고서 SELECT는 비원자 스냅샷 |
| R14 | HIGH | 예전 API·deprecated 경로를 새 수집기로 잘못 실행 | CONFIRMED multiple collectors | import_*/sync_*/reclassify_*/legacy gate | 코드 존재와 현재 허용된 운영 경로를 구분; 일괄 재실행 금지 |
| R15 | MEDIUM | FK 없는 논리 건물 ID 연결 누락·오연결 | CONFIRMED metadata | user_favorites 등 논리 참조 목록 | 주소/소유권/존재 검증 계약을 별도 분석; 데이터 변경 없음 |
| R16 | HIGH | 개인정보·서류·전화·채팅·토큰의 신규 공개 노출 | CONFIRMED columns; INFERRED future risk | users/operator_lodging/chat/member_documents/password_reset_tokens | 공개/비공개 객체 경로·소유권 검증과 digest-at-rest 유지 |
| R17 | MEDIUM | 관광 원본 기간·지표 불일치 및 공개/인증 원본 혼동 | CONFIRMED validation code | tourism_stats.source_period; monthly manifest; TYPE_RULES | 관광 수요·HS-OI 등을 다른 기간 매출 지표로 단정하지 않음 |
| R18 | HIGH | 예약/달력/재고/정산 시스템을 기존 listings 존재만으로 완성 처리 | INFERRED readiness gap | listing_requests/slots/business_room_inventory는 기존 업무 모델 | 신규 단기임대의 일정·예약·취소·정산 정책은 현재 미검증/새 설계 필요 |
| R19 | MEDIUM | 대형 단일 파일의 영향 범위와 정적 조사 한계 | CONFIRMED file size/static inventory | app.py/main.js/admin inline JS; dynamic dependencies | routes.csv에서 INFERRED/UNKNOWN 구분; 런타임/권한 실증은 별도 단계 |
| R20 | MEDIUM | 워크스페이스 조사와 현재 배포 버전의 차이 | CONFIRMED separate source/build context | deployment metadata does not prove exact source SHA | 본 보고서는 코드 snapshot+운영 schema 조사이지 배포 코드 diff 검증이 아님 |
