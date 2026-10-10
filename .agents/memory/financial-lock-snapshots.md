---
name: Financial lock snapshots
description: PostgreSQL join reads after waiting for a separate financial-record lock.
---

결제 원장 잠금과 예약 상태 조회를 분리한다. 변경되지 않은 원장 행만 잠그는
JOIN 문장에서 오래 기다렸다고 해서 JOIN된 예약의 상태도 최신으로 읽히는
것은 아니다. 잠금을 얻은 다음 별도 문장에서 예약 상태를 다시 읽는다.

**Why:** 동시 지급 통지의 두 번째 처리에서 증빙은 이미 적재되었지만, 잠금
대기 전 JOIN snapshot의 결제대기 예약 상태를 반환하여 확정 여부가 틀릴 수 있다.

**How to apply:** READ COMMITTED에서 부모 원장 잠금 뒤 자식 예약·결제 상태를
반환하거나 멱등 재시도를 처리할 때 새 statement snapshot으로 읽고, 동시
재전송 검사는 모든 응답의 상태도 확인한다. 중복 행 개수만 검사하지 않는다.
