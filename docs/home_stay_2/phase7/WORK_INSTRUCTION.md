# Work → Replit: 사용자 Phase 7 — 가격/Calendar Engine

Phase 6 전체 27개 검사·내부 Work 검토·immutable 완료 checkpoint·GitHub 개발
브랜치 exact commit/tree·main 불변 확인 뒤 시작한다. 사용자 원문 7절을 따른다.

숙박은 날짜별 일일 요금, 평일/금/토/일/특정기간 일괄 설정과 날짜별 override.
비숙박은 주·월 요금과 미래 변경. 미래 가격 변경으로 확정 snapshot이 달라지지 않는다.
Phase 6 등록·원래 분류/가격 snapshot·현재 승인/사업장/권한을 재사용한다.

권장 개발 정책은 Asia/Seoul·KRW, 체크인 포함/체크아웃 제외, 주=7일,
월=체크인 기념일 기준 다음 달 같은 날짜(없는 날짜는 그 달 말일)로 한다.
전체 주/월 기간 조합만 허용하고 부분 기간의 임의 일할 환산은 하지 않는다.
여러 유효 조합은 최소 총액을 명시적으로 선택한다. 표시 숙박료는 운영자 입력의
필수비용 포함 총액이며 별도 청소/관리/서비스 비용을 숨겨 붙이지 않는다.
보증금·실제 수납/세금계산/정산은 후속 Phase로 분리한다. 개발에서 권장 정책을
결정한 것이 실제 법률·과세 검증이나 실제 PG 승인은 아니다.

가격은 양의 정수 원화, 누락/0/없는 기간/막힌 날짜는 견적 불가다. 날짜 누락을
0원으로 메우지 않는다. 변경 버전은 append-only이며 원본 등록 revision을 묶는다.
등록 revision/분류가 바뀌면 기존 가격을 새 등록에 조용히 재사용하지 않는다.
미래 가격만 변경하고 서버 지역 날짜·현재 actor/business를 다시 확인한다.

실제 격리 PostgreSQL/API/UI에서 일괄 설정·override·휴무/예약불가 날짜·주월 변경,
소비자 기간 총액과 고정 snapshot의 불변성·계정/사업장/공개 범위를 검사한다.
Booking confirm/hold 경쟁 제어 자체는 Phase 10이며 snapshot foundation을 확정예약
구현 완료로 기록하지 않는다. 가격 소비자 read adapter를 Phase 5의 safe query 계약에
연결하고 실제 기간 총액 검색에 재사용할 수 있게 한다.

운영 migration·실제 결제·App Storage·배포는 승인 Gate를 열지 않는다.
