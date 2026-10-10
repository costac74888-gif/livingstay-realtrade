# 기존 구조의 실제 사용 조사와 판단

조사 방식: 인계 commit의 schema 선언, SQL 호출, route/decorator, 순수 함수
소스를 읽었다. app/db initializer import, HTTP 호출, 운영 DB 조회는 하지 않았다.
아래는 **현재 소스의 사용 사실**이다. 운영 DB의 실제 schema/row 상태는 미확인이다.

| 기존 구조·소스 증거 | 실제 의미/사용 관계 | 재사용·확장·신규 판단 |
| --- | --- | --- |
| db.py master_buildings; app.py public_building_search, admin_buildings_create, submit_building | 숙박 원장 ID가 거래·공매·신고·지도·사업장·매물의 공통 연결점. 공개 /api/buildings/search는 이 원장만 조회. 관리자 추가/사용자 건물 제출은 master를 INSERT/UPDATE할 수 있음 | **보존·참조만**. 전체 건물 후보 저장소로 확대하거나 기존 등록 route를 재목적화하지 않음 |
| db.py building_requests; app.py submit_building, admin_building_requests_list | 신규 숙박 건물 검증/용도 정정/명칭 검토 업무와 master 편입 결과를 기록 | 새 전체건물 조회 후보·단기임대 등록 큐로 재사용하지 않음. 기존 검증 흐름과 승인 이력 보존 |
| db.py listing_requests; app.py create_listing_request, public_listings; listing_extensions.py public_channel_sql | user→master 건물의 매물의뢰. 매매/전세/월세/단기임대, direct/broker, 승인 게시, 배정·철회·이력·사진·채팅 연결. price_krw 등의 실제 단위는 이름과 달리 **만원** | 예약 가능 상품과 분리한 **신규 매물** 설계. 기존 단기임대 문자열을 새 예약 상품으로 자동 전환하지 않음 |
| db.py listings; app.py /api/admin/listings 관리 경로 | 기존 중개사 매매·전세·월세 목록. master/agent FK, 만원 가격 | 단기 예약 상품 원장으로 재사용하지 않음. 기존 목록/관리 URL 유지 |
| db.py slots | master→agent 입점 슬롯, active/waiting/expired, 대기순번·월회비 | 예약 날짜 슬롯이 아님. 새 날짜 재고와 공유하지 않음 |
| db.py business_room_inventory; app.py my_room_inventory, create_my_room_inventory, _owned_listing_request | listing_request→객실 라벨, 공실/입실·계약만기·월세·채널. 소유 사용자 및 중개사 사업장 컨텍스트 검증. 건물 상세에서도 집계하여 표시 | 장박 운영 원장 보존. 새 재고 pool과 자동 동기화/전환 없음. 향후 옵트인 읽기전용 출처 연결만 검토 |
| db.py booking_url_requests; app.py 건물 상세의 승인 OTA 링크 조회, operator_booking_url_requests_list | operator→master의 외부 booking_url 승인·만료·갱신 기록 | 내부 예약/가격 스냅샷으로 재사용하지 않음. URL은 예약 채널이지 법적 숙박분류가 아님 |
| db.py users, account_role_memberships, account_business_memberships; listing_extensions.py broker_context/public_channel_sql | 로그인 주체와 복수 역할·사업장 연결은 이미 분리되어 있음. 기존 partner row 및 승인 경로 유지, 이메일만으로 자동 연결하지 않음 | **로그인 주체·기존 멤버십 참조 재사용**. 별도의 건물/호실 권리 grant를 확장 관계로 설계. provider/user_type/인증 휴대폰만으로 등록권을 부여하지 않음 |
| db.py business_building_verifications | user→master별 영업신고번호 인증 캐시 | 소유권/전대 동의/호실 예약 권한 전체를 뜻하지 않음. read-only 영업근거 참조 가능하나 자동 권한 승격 금지 |
| lodging_categories.py, lodging_classification.py; db.py 숙박 원장·복수 신고 연결 | 법적 영업분류와 건축 용도, 활성/폐업 신고 및 복수 허가의 별도 의미 | 기존 분류·원장 변경 없이 출처/결정 버전을 새 매물의 분류 근거로 참조. 한 건물의 대표 신고를 모든 호실에 전파하지 않음 |
| app.py _apply_limited_whole_listing_privacy, _whole_listing_checklist_data; 기존 privacy-ui 검사 | 제한공개에서 building ID·좌표·사진·전화·자동 보정값 등 제거. 파생 정보와 join도 위치를 드러낼 수 있음 | 기존 필터 무변경. 새 공개 DTO는 독립 allowlist, raw ID/주소/호실/사진 EXIF/자유텍스트/근거 join을 포함하지 않음 |
| app.py 각 기존 route, public_api_client.py, 기존 수집·쿼터·승격 코드 | 운영 기능 및 Relay 경계, 원장 동기화·승격은 별도 책임 | source 무변경. 후보 설계를 위해 수집 범위를 확대하거나 Relay allowlist/키/설정을 바꾸지 않음 |

## 핵심 판단 근거

1. 기존 master ID에 다수의 운영 FK가 있으므로 이를 일반 건축물 ID로 교체하면
   거래·공매·신고·관심·지도 연결이 깨진다. 기존 sequence 재설정/재번호도 금지한다.
2. 같은 주소/PNU는 여러 동·호실·표제부를 가리킬 수 있다. 주소명/건물명 유사도나
   단순 ID 존재 여부로 legacy를 연결하지 않는다. 공식 건물 식별정보 대조 및
   양쪽 유일성을 확인하지 못하면 검토 대기, 기존 행은 그대로 둔다.
3. 기존 room/slot/link의 이름만 보고 예약 재고로 재사용하면 날짜 충돌 방지와
   권한 모델이 빠진다. 새 상품·재고·확정예약은 별도 생명주기가 필요하다.
4. 기존 가격은 만원 숫자·희망가 문자열 혼합이다. 새 가격은 명시적 KRW 원 정수다.
   implicit ×10,000 변환이나 기존 예약 없는 매물의 자동 예약 전환을 하지 않는다.
5. 기존 로그인 이력·복수 사업장 모델은 유지한다. 새 관계는 user FK와 검증된
   사업장 컨텍스트를 참조하되, 전 건물/타 호실 권한으로 확대하지 않는다.

관계·불일치 동작은 phase1-graph-contracts에서 fixture로 검증한다.
원장 불변·URL·권한 구현 무변경의 추가 근거는 인계 commit 대비 변경 파일 목록과
기존 전체 등록 회귀검사다. 운영 DB 실측 결과라고 주장하지 않는다.
