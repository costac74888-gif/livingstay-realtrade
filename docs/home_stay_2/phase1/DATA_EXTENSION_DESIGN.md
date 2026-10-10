# 데이터 확장 설계 — 미적용 논리 모델

**SQL/migration 파일이 아니다.** 아래 이름·제약은 신규 namespace의 설계 후보다.
db.py, schema version, 현재 ORM/SQL/route/화면에는 반영하지 않는다.
PK는 별도 UUID, 새 금액은 KRW 원 단위 BIGINT, 날짜는 사업장 로컬 DATE,
기록시각은 TIMESTAMPTZ로 제안한다. 기존 SERIAL/sequence/ID/금액 해석은 유지한다.

## 조회 후보 → 등록 건물 → 단기임대 매물

```text
공식 조회 근거/다중 식별자 → hs2_building_candidates (조회 후보)
                            ├─ 0..1 hs2_registered_buildings (물리 건물)
                            │        ├─ N 등록자/사업장/호실 범위 grants
                            │        ├─ N inventory pools (판매 가능한 동일 물리 재고)
                            │        └─ N hs2_stay_listings (독립 상품)
                            └─ 검증된 선택적 read-only link → 기존 master_buildings

stay_listing → append-only 분류 결정/요금 버전
stay_listing → 향후 예약 → 불변 가격 스냅샷
```

조회 후보는 숙박뿐 아니라 원룸·오피스텔·아파트·빌라·연립·다세대·다가구·단독·
도시형생활주택·농어촌·한옥·캠핑·상가·창고·기타/복합을 허용한다.
**후보 허용 ≠ 등록 검증 완료 ≠ 운영 적법성 ≠ 예약/공개 승인**이다.
전체 건물 후보를 master에 INSERT하거나 숙박 통계 분모로 합산하지 않는다.

후보에는 미확인/모호 상태도 저장할 수 있다. 등록 건물의 확정 연결 전에는
정규 물리 건물 identity가 유일해야 한다. 공식 건물관리번호/표제부 PK와
출처/version의 대응을 보존한다. PNU·도로명·상호만으로 한 동을 확정하지 않는다.
provider별 ID가 같다는 이유로 병합하지 않으며, 확인된 crosswalk만 사용한다.
같은 주소의 다른 동은 다른 후보, 같은 동의 확인된 별칭은 다중 식별자로 표현한다.

## 설계 관계·필드·제약

| 설계 대상 | 핵심 필드·관계 | 제약/생명주기 |
| --- | --- | --- |
| hs2_building_candidates | id, confirmed_identity_key(nullable), lookup_state, 건축 용도/주소/좌표(private), evidence/version/조회일 | 확정 identity만 unique. 실패/모호는 review. 법적 분류와 별도. 조회 캐시 만료는 등록/원장 삭제 아님 |
| hs2_candidate_identifiers | candidate_id FK, source, external_key, proof_version, status | 검증된 (source, external_key) unique. 서로 다른 식별자 체계의 대응 근거 기록 |
| hs2_candidate_master_links | candidate_id FK, 기존 master_id FK, identity 근거/version, review_state | verified 링크는 양쪽 유일성 필요. 신규→legacy 삭제 cascade 금지, 기존 master 수정 금지. 중복 master는 검토로 보존하고 자동 통합/재번호하지 않음 |
| hs2_registered_buildings | id, candidate_id unique FK, registration_state, 검증 좌표 근거/version | 하나의 확정 물리 건물에 하나의 등록 건물. master_id는 등록 필수 조건 아님. 여러 소유자·여러 매물 가능. 폐기/철회는 soft state |
| hs2_registration_grants 및 grant-unit 관계 | registered_building_id FK, users.id 참조, 선택적 기존 사업장 membership 근거, role, 권리 근거, 승인상태/기간, 허용 inventory keys | 로그인 provider/휴대폰/영업신고만으로 승인하지 않음. 서버가 근거/활성 사업장/역할/대상 호실을 검증. 철회는 감사 이력 보존, 후속 쓰기는 거절 |
| hs2_inventory_pools | id, registered_building_id FK, 물리 unit key, 단위/수량, 권리/공유 근거 | 동일 물리 재고는 여러 매물/채널에서도 같은 pool. 다른 건물과 pool 공유 금지. 기존 business_room_inventory는 자동 이관하지 않음 |
| hs2_inventory_pool_members | parent_pool/child_pool FK, 범위 근거 | 건물전체와 호실의 중첩은 공유재고 관계로 명시. cycle 금지. 향후 전체/호실 동시 예약은 관련 pool 전체 잠금·경합 검사 필요 |
| hs2_stay_listings | id, 별도 random public_id unique, registered_building_id FK, creator users.id, inventory_pool FK, 공개범위·상태, 현재 분류 결정 참조 | draft/review/published/withdrawn 생명주기. listing_requests/listings와 별도 ID·채번. 기존 의뢰를 자동 공개/승격하지 않음 |
| hs2_listing_classification_decisions | listing_id FK, lodging/non_lodging/unresolved, 영업분류, 건축 용도, channel, permit/evidence refs, 결정 version/주체/시각 | append-only. 근거는 해당 대상·호실과 일치. 불명·상충·폐업만 존재할 경우 booking은 review. 숙박 분류가 적법성/내국인 수용 허가를 뜻하지 않음 |
| hs2_tariff_versions 및 date/period rows | listing_id FK, version, KRW currency, 숙박 날짜별 요금 또는 비숙박 주/월 요금, 적용 기간, terms version | 공개/사용된 version 불변. 날짜 override는 적용된 날짜값으로 저장. 기간 중복/누락/음수/소수/0원 implicit fallback 금지 |
| hs2_reservations (향후) | guest users.id, listing_id/pool, 선택 날짜·사업장 TZ, status, idempotency key, quote version | (guest, 요청키) unique. 동일 키 다른 본문 거절. hold/확정 경합은 물리 재고별 원자 처리. 이번 단계에서 저장/확정 기능 없음 |
| hs2_reservation_price_snapshots 및 line items (향후) | reservation_id unique FK, 선택 날짜, classification/evidence version, tariff/terms version, TZ, 통화, line units/금액/기간, fee/tax/discount 구성, 합계 | append-only 불변 금액. 확정 당시 전체 구성 복사. 요금/분류/정책 변경 시 재계산·소급 UPDATE 금지. 취소/환불/정산은 별도 감사 event, 원본 snapshot 삭제 금지 |

FK 삭제 정책은 기존 원장에 신규 cascade를 추가하지 않는 RESTRICT/soft-state를
원칙으로 한다. 기존 FK 자체는 이번 작업에서 바꾸지 않는다. 실제 제약·index·
schema diff·lock/rollback·runtime 초기화는 **별도 승인된 후속 설계/검사** 대상이다.
정확한 SQL과 운영 schema 호환성은 검증하지 않았으며 DDL은 생성/실행하지 않았다.

## 체류·요금·확정가격 계약

1. 영업분류, 건축 용도, 채널은 별도 차원이다. Airbnb라는 채널만으로 숙박 또는
   비숙박을 결정하지 않는다. 도시민박/농어촌/캠핑의 검증된 숙박 근거는 1박 후보다.
   미확인은 자동 7일 분류 대신 unresolved다.
2. 숙박은 check-in 포함, check-out 제외 **최소 1박**, 날짜별 가격.
   비숙박은 같은 로컬 날짜 구간 **최소 7일**, 주·월 가격.
   UTC 시간 차이를 24로 나누거나 1개월을 30일로 자동 정의하지 않는다.
3. override의 원본/요금 version과 적용된 날짜별 가격을 snapshot에 포함한다.
   비숙박 기간 요금 변경은 적용 기간과 resolved 기간 경계로 분리한다.
4. 부분 주/월과 월 경계 알고리즘은 아직 미승인이다. 순수 계약에서 full week는
   7일 경계를 검사하며, 월은 reviewed explicit period를 제공한 fixture만 허용한다.
   이 fixture는 실제 월 계산 사업정책의 승인/선택이 아니다.
5. 모든 비용/할인/세금/보증금의 포함 여부·통화·총액 정책이 확정돼야 실제
   확정예약이 가능하다. prototype의 adjustments는 명시적 fixture 입력으로 복사되며,
   생략을 0원 정책으로 간주하지 않는다. 보증금의 수납/환불 의미는 미정이다.
6. 확정가격 snapshot은 원본 요금/정책/분류 객체와 독립된 불변 line/구성이다.
   후속 요금표 수정·삭제 또는 분류 변경이 과거 예약 금액을 바꾸지 않는다.
   취소/정정 금액은 새 event로 보존하며 원본 예약 확정값을 덮어쓰지 않는다.

## 기존 동작과 접점

- 기존 조회/지도/API/관리자 URL은 변경하지 않는다. 새 조회는 미래 별도 API와
  private DTO를 설계할 대상이며 /api/buildings/search를 전체 건물로 바꾸지 않는다.
- 기존 공개·제한공개 채널, 매물의뢰 배정·철회·채팅·관심·이력은 그대로 둔다.
- 새 limited DTO는 public_id/kind/withheld만 반환하는 최소 계약이다.
  정확한 주소·좌표·건물명·원장/후보/등록 ID·호실·전화·사진 EXIF·근거 join·
  자동정보·자유텍스트로 우회하지 않는다. full 공개는 별도 승인 없이는 미구현이다.
- 기존 숙박 원장 통계/실거래/공매/수집/승격/Relay는 새 후보층의 영향 밖에 둔다.
  단기임대·매매·영업권·공매 레이어 통합 구현은 이번에 하지 않는다.
- 신규 알림은 기존 outbox/수신동의 모델을 향후 검토하되, 지금 신청 trigger나
  이메일/SMS/외부 booking platform/PG 연동을 추가하지 않는다.

## 독립 값 계약의 의미

hs2_design/domain.py와 pricing.py는 위 설계의 일부를 fixture로 실행하는 reference
contracts다. storage adapter, 서버 권한 검사, 예약 확정 엔진 또는 가격 서비스가 아니다.
호출자가 보내는 approved/reviewed/evidence 값을 신뢰하는 HTTP/API를 만들면 안 된다.
미래 서버는 검증된 원장·활성 권한·해당 대상·정책 version을 독립적으로 조회해야 한다.
실제 계약 검사와 기존 등록 회귀 결과가 PASS라도 후속 2~18단계 기능 완료를 뜻하지 않는다.
