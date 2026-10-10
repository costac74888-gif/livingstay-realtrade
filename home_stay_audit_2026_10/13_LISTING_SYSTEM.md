# 기존 매물·의뢰·영업권·채팅 시스템

조사 기준: 2026-10-10 (Asia/Seoul). 코드 스냅샷은 워크스페이스 HEAD `8285754f85ef` + 현재 파일이며 운영 배포 소스와 동일한지 UNKNOWN입니다.

**CONFIRMED** = 코드·메타데이터·SELECT로 확인. **INFERRED** = 정적 호출 후보/설계 분석. **UNKNOWN** = 이번 단계에서 확인하지 못함. 코드 존재는 서비스 실행/데이터 최신성의 증명이 아닙니다.

DB 대상: `executeSql(environment="production")` 읽기 전용 운영 조회 경로. DB 지문은 이전에 검증된 운영 지문과 일치(CONFIRMED); 연결 문자열·계정·호스트 값은 수집하지 않았습니다. 서로 다른 SELECT는 한 트랜잭션 스냅샷이 아니며 기존 수집기가 계속 실행될 수 있습니다.

소스 import/실행, 테스트, 앱/관리자 URL 방문, 외부 API 조회, 수집·동기화·마이그레이션, 설정 변경, Git commit/push는 실행하지 않았습니다. 신규 보고서 폴더와 `/tmp` 조사 보조파일만 작성했습니다.

## 서로 다른 엔티티
- CONFIRMED `listing_requests`는 user_id/master_building_id/deal_mode·deal_type·transaction_target·publication_status/disclosure_scope를 보유한 의뢰/직거래/중개 매물 업무 원장.
- deal_mode(게시 방식)와 transaction_target(개별 호실/건물전체/영업권 등 거래 대상)은 독립. 중개의뢰를 자동 공개 매물로 바꾸면 안 됩니다.
- CONFIRMED `listings`는 별도 legacy/general table이므로 이름만으로 핵심 공개 매물 원장으로 판단하면 안 됩니다.
- CONFIRMED `auction_items`는 public source 공매 원장, 일반 판매자 listing ID가 아님. source item/회차/master ID를 분리.

## ID·연락·이미지·가격·주소
listing_requests.id/user_id/master_building_id/routed_agent_id/broker_agent_id, 가격 price_krw/monthly_rent_krw/deposit_krw 등, area_sqm/dong/ho 및 description, verified_phone, 공개 상태·범위·등급. 이미지 listing_photos → 저장소 key; 건물 주소·좌표는 master join. 제한공개는 자동 건물 값도 익명화 우회를 만들지 않아야 합니다. CONFIRMED listing_requests.price_krw는 이름과 달리 만원 단위입니다(app.py:13082/13118/13833; main.js:7279). 각 가격/deposit/rent/권리금 및 공매 원 단위는 개별 파서·UI 계약에 따라 검토하며 컬럼명만으로 자동 환산하면 안 됩니다.
영업권은 key_money/운영 매출/대출 승계/객실/OTA·단기 비율/business_rights_info 등 별도 값; 부동산 소유권 거래와 혼합하지 않습니다.

## 관계·상태·작업
등록/수정/삭제·초안·검수·비공개·철회·배정·매물 이력·문의/채팅·관심 listing_likes·알림 경로가 있습니다. 상태 변환은 role/소유권·검수 조건을 갖습니다. 철회 상태는 기록·채팅·배정을 지우는 작업과 다르며 삭제 archive가 존재합니다. UI/API의 exact 계약은 routes.csv 및 schema의 CHECK/columns 참조. 본 조사에서는 개별 매물/전화/채팅 내용을 읽지 않았습니다.

## 원장 규모/테이블
| table_name | row_count | row_count_basis |
| --- | --- | --- |
| business_room_inventory | 1 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| buy_requests | 1 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| chat_messages | 11 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| chat_rooms | 6 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| listing_checklist_progress | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| listing_likes | 7 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| listing_photos | 12 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| listing_request_deletion_archive | UNKNOWN | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| listing_request_history | 12 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| listing_requests | 28 | CONFIRMED COUNT(*) at query time |
| listings | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |
| slots | 0 | INFERRED pg_class.reltuples estimate; -1 means UNKNOWN |


## 신규 단기임대 확장 의견 (INFERRED)
기존 매물/관심/문의/사진 UI를 재사용할 여지는 있으나 기간 예약·재고·가격/보증금/관리비·취소 환불·결제 정산·단기 사용 계약의 완성 여부는 UNKNOWN입니다. `slots`/운영 객실 표가 있다고 예약엔진이 있다고 단정하지 않았습니다. 기존 매물을 지우거나 schema를 새 모델로 덮어쓰지 않았습니다.
