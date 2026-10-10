# Phase11 — 내부 Work 금융 기반 검토

Native S17 결제검증 기반을 별도 append-only financial contract/events와
실제 기존 bookings FK snapshot에 연결한다. 실결제 실행·실제 PG 연결이 아니다.

- 소비자 본인 결제대기 예약의 reviewed 정책을 미리 계산하여 gross/deposit/
  payable/host fee/VAT/net을 보여주고, 해당 정책·금액 hash에 동의해야 계약을
  만든다. 정책 변화는 재동의, 동일 계약 재진입은 원래 snapshot이다.
- gross200,000/deposit50,000의 owned 증빙에서는 payable250,000, 초기 플랫폼
  fee0, VAT0, 명시적인 sandbox PG 비용0, host net200,000이다. 초기 플랫폼
  요율은 원문0%이며 향후 fee/VAT 엔진과 별도 PG 비용을 구분한다. 5%/VAT10%는
  엔진의 별도 테스트 사례일 뿐 초기 적용 요율이 아니다. 개발 검토안은
  법무/회계/실서비스 검토·실행 승인과 다르다. 미설정 deposit/policy는 오류다.
- provider adapter의 서명·delivery 시간·정확한 계약/통화/총액을 확인한다.
  economic event hash는 재전송 delivery timestamp와 구분하고 event/reference
  잠금·unique 제약으로 경합·동일 재전송·다른 내용/대상 재사용을 막는다.
- 확인된 증빙 적재와 예약 확정은 같은 transaction이다. source/권한/예약기한이
  잠금·증빙 확인 중 달라지면 SAVEPOINT로 예약 변경만 되돌리고 verified money
  fact는 late_capture/refund review로 보존한다. 금액 증빙을 잃거나 재고를
  되살리지 않는다. 증빙 부재·client paid·원장/가격 변경은 허용하지 않는다.
- READ COMMITTED의 contract lock 대기 뒤 booking 상태는 새 문장 snapshot에서
  다시 읽는다. 모든 동시 retry 응답이 확정 상태를 정확히 반환하는지 검사한다.
- 입실일 전의 유료 취소는 별도 immutable cancellation fact/refund review와
  슬롯 해제로 처리한다. 원래 confirmed booking의 역사·price identity는 유지하고
  소비자 예약 API에 cancelled_paid를 반환한다. 환불 검토는 실제 환불이 아니다.
  입실일 이후는 수동 검토로 제한하고 늦은 지급은 전액 환불 검토 대상으로 둔다.
- 정책의 퇴실1일 뒤 host net/7일 뒤 escrow deposit은 서로 다른 review 항목이다.
  날짜 기준은 Asia/Seoul이며 client 날짜를 쓰지 않는다. 중복 review는1건이다.
  공제/반환/host payout 전송을 자동 실행하지 않는다. execution port는 승인
  부재 오류를 반환하며 기본적으로 실제 돈을 옮길 adapter 자체가 없다.
- 소비자/운영자 금융 UI는 실제 API에 연결되어 preview 동의→계약 생성/재진입,
  기록·검토 요청·사업장 목록을 표시한다. sandbox/실행 차단을 명시하고
  checkout/paid/송금/환불 완료를 client에서 꾸미지 않는다.

## 범위·검증 제한

owned SQL/Chromium은 실제 저장·잠금·정확 금액과 UI를 검증하지만 mocked
지급 증빙은 실제 PG가 아니다. 실제 auth/provider/storage/host mount/운영
source는 후속 통합과 명시적 운영 승인 영역이다. production migration·실제
PG/settlement·publish를 실행하지 않았으며 기존 smoke/api 문제도 그대로다.
실제 환불/송금 provider callback 연결과 승인 workflow는 운영 Gate와 후속
Admin/Policy 단계에서 검토하며 지금 현금 실행 완료로 표시하지 않는다.
