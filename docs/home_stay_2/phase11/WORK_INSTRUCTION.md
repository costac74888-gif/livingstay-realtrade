# Work → Replit: 사용자 Phase11 — Payment/Deposit/Settlement 기반

Phase10의 전체40개 검사·내부 검토·immutable checkpoint·개발 원격 일치/
main 불변 확인 후 진행한다. Native S17-A01/S17-A02의 검증 가능한 지급 원장과
검증된 결제→예약 확인 경계를 구현한다. 실제 PG를 연결/청구하지 않는다.

provider-neutral payment adapter와 append-only 결제/환불/보증금/정산 원장을
구현한다. 서명 확인·중복 event/reference·대상/금액/통화 불일치·만료/취소 후
늦은 지급·반복 webhook·정산/환불 중복·상태 경합을 실제 PostgreSQL에서 검증한다.
외부 결제 증빙은 서버 adapter만 기록하며 client paid/amount 상태로 예약을
확정하지 않는다. request source/receipt와 승인/결제 기한은 잠금·외부 증빙
확인 뒤에도 DB 시각으로 재확인하여 대기 중 만료를 우회하지 못한다.

보증금은 매출·사업자 지급과 별도 escrow 성격 원장으로 분리한다. 운영자가
확인한 명시적 금액이 없으면 미설정/결제 차단으로 표시하고 무료0원으로
대체하지 않는다. 파손/공제는 소비자 고지·명시 근거·검토 없이는 자동 적용하지 않는다.
수수료·세금·환불/보증금 반환/정산 일정은 버전·검토 근거가 있는 개발 정책으로
계산하며 과거 확정 금액과 정책 snapshot을 바꾸지 않는다.

초기 플랫폼 수수료는 원문대로0%다. 향후 관리자가 변경할 수 있는 수수료와
해당 수수료 VAT 계산 엔진은 유지한다. PG 비용은 별도 검토된 금액이 필요하고
미확인 값은0원으로 대체하지 않는다. stay gross에서 fee/VAT/PG를 제외한 금액만
host payout으로 계산하고 escrow deposit은 제외한다. 입실 전 취소는 stay 전액
환불, 입실 이후는 수동 검토로 보류한다. deposit 공제 없는 반환은 퇴실7일 후,
host settlement는 퇴실1일 후 지급 검토 대상으로 만든다. 이 정책은 법적 인증/
실행 승인이 아니며 실제 서비스 전 관리자가 법무·회계·PG 조건을 확인해야 한다.

소비자/운영자에게 결제 대기·검증된 지급·refund/escrow/payout 검토 상태와
정확한 분리 금액을 UI로 보여준다. live execution과 sandbox 증빙은 분명히 구분한다.
actual PG/settlement approval Gate는 NOT_APPROVED이므로 실제 checkout/
refund/deposit transfer/host payout 실행은 실패한다. integration 연결 제안·
비밀값 요청·실제 제공자 연결은 별도 승인 전 하지 않는다. 재사용 가능한
adapter/원장/계산 정책과 owned test 증빙만 개발한다.
