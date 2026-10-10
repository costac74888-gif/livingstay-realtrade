# Phase 7 — 내부 Work 구현검토

원문 가격/Calendar 단계에 actual acceptance 세 그룹을 연결한다. 외부 독립
감사·운영 승인·Booking 완료를 의미하지 않는다. 전체 검사의 최종 영수증은 state다.

- 숙박 일별 요금은 기본 1박 가격과 명시적인 날짜 override로 계산한다. 요일별/
  평일/금토일/특정기간 일괄 입력은 실제 날짜로 저장하므로 특정일 변경이 우선한다.
- 비숙박 7일 주·입실기념일 월을 정확하게 조합한다. Jan31→Feb말→Mar31로 계산하며
  30일 환산·부분 주월 일할은 없다. 전체 월 접두기간과 나머지 전체 주의 유효 조합
  중 최소 총액, 동률 월 우선을 선택한다. 기간 시작일의 당시 요금으로 각 줄을 만든다.
- 가격 0/누락/비정수·기간 밖·최소일수 미달·막힌 날짜는 명시적으로 실패한다.
  필수비용 포함 운영자 확인 없이 견적을 공개하지 않고 보증금은 포함됐다고 하지 않는다.
- 소스 등록 revision과 요금 revision을 함께 fence하고 실제 PostgreSQL에
  append-only 요금 버전을 저장한다. 수정된 등록에 기존 요금을 몰래 재사용하지 않는다.
- 공개 견적은 원래 Phase6 현재 승인/365일/계정/사업장/권한 필터를 쓰고 row lock 뒤
  다시 확인한다. 내부 등록/분류/운영자 ID를 공개하지 않는다. CSRF와 trusted quote
  budget/inventory/clock adapter는 명시적으로 요구한다.
- Phase5 소비자 검색의 complete/public_price_allowed/source_version 계약을 실제
  계산과 연결한다. 누락 견적은 None으로 유지하여 필터에 0원으로 들어가지 않는다.
- 원래 Phase2 price_snapshot/save_fixture_snapshot 및 classification/tariff FK를
  그대로 사용한다. 저장 이후 새 요금 변경·snapshot UPDATE가 원래 총액을 바꾸지 못한다.
- 실제 Chromium 1280/390에서 save→reload→override→quote→close/open→주월 견적을
  검사했다. 서버의 완료 응답 뒤 결과를 읽고, 충돌 쓰기를 거부하며 stale 금액을 지운다.

## 경계

원문 Native S09/S10의 hold/Booking confirm 경쟁 제어와 실제 수납은 후속 단계다.
freeze_fixture는 append-only snapshot foundation의 내부 개발 검사로만 제공되며
웹에서 예약확정으로 노출하지 않는다. inventory callback의 fixture는 실제 예약 없는
격리 원장을 뜻하며 실제 재고/hold adapter는 Booking 단계에서 연결한다.
등록된 실회원 로그인·운영 App Storage·공공 API/지도 SDK·production migration·
실제 PG·publish를 검사하거나 실행하지 않았다. 앱 본체 route mount도 아직 없다.
fixture quote budget의 허용값을 실서비스 rate-limit 구현으로 주장하지 않는다.
기존 smoke/api workflow 실패는 이 레지스트리 PASS로 해결되었다고 주장하지 않는다.
