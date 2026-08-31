---
name: 실거래 동기화 deadlock
description: RTMS 수집이 스키마 초기화나 다른 DB 작업과 충돌할 때의 재시도·커밋 원칙
---

스키마 초기화에서 발생한 PostgreSQL deadlock은 버전 불일치로 오인하지 말고 바깥의 제한된 backoff 재시도 경로로 전달한다. 거래 적재는 시군구 전체가 아니라 시군구·월 단위로 commit하며, deadlock이면 이미 받은 API 응답을 재사용해 그 월만 rollback·재적재한다.

**Why:** 긴 트랜잭션이 API 호출 사이의 대기 중에도 `master_buildings` 잠금을 보유하면 스키마 DDL이나 다른 읽기 작업과 교착될 수 있다. API를 다시 호출하는 재시도는 일일 할당량도 이중 소모한다.

**How to apply:** 거래·체크포인트·실패큐 정리는 한 월의 같은 commit 경계에 둔다. rollback 시 누적 통계를 원복하고, DB 예외를 내부에서 삼켜 aborted 트랜잭션을 계속 쓰지 않는다. 이메일 같은 외부 부작용은 commit 성공 뒤에만 실행한다.