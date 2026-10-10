# Phase18 내부 Work 실행 지시 — Cutover/Open

Phase17 COMPLETE·최종55그룹 PASS·같은 원본 fingerprint의 내부 검토·
개발 원격 정확한 commit/tree/tag·main 불변 영수증 확인 뒤 시작한다.

사용자 원문 Human Approval Gate A(운영 DB migration),
B(실제 PG/결제/정산 활성화), C(실제 운영 전환/배포)를 따로 유지한다.
권장 선택의 자동 진행을 이 승인으로 해석하지 않는다. 실제 승인과 해당
실행 근거가 없으면 Phase18을 BLOCKED로 남기고 다음 Phase나 완료로 꾸미지 않는다.

현재 수행 가능한 범위는 원본·개발 checkpoint·검사 증거·차단 조건을
정리하는 것이다. 운영 DB 쓰기/접속 변경, 실제 결제/환불/정산/발송,
기존 앱에 새 main mount, main 병합, 운영 게시를 수행하지 않는다.
실제 host session/SDK/provider 연결·도메인·운영 환경 검증은 미확인이다.
모의 adapter와 owned SQL/browser 성공을 실제 연결 성공으로 바꾸지 않는다.

차단 원인·각 승인 범위·추가 실제 증거 목록을 남기고 개발 브랜치에 정확히
백업한다. 준비 체크리스트는 actual Cutover/Open acceptance가 아니다.
