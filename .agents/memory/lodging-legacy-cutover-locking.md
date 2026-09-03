---
name: 숙박 legacy 컷오버 잠금
description: 승인 기반 legacy 수집 종료가 직접 실행과 동시 실행 경쟁을 안전하게 막는 원칙
---

기존 수집 종료는 상위 스케줄러의 설정 확인만으로 보장하지 않는다. 실제 수집기 프로세스가 전체 실행 수명 동안 DB shared advisory lock을 보유하고, 관리자 종료 승인은 같은 lock의 exclusive 모드에서 설정을 커밋해야 한다.

**Why:** 상위 실행기 확인과 실제 수집기 시작 사이에는 경쟁 구간이 있고, 직접 CLI·재기동 복구 경로가 상위 확인을 우회할 수 있다. 수집기 자체의 잠금이 최종 방어선이어야 한다.

**How to apply:** 새 legacy 수집 진입 경로도 반드시 공통 writer gate 안에서 status claim 전에 종료 설정을 확인한다. 최신 manifest와 무회귀 관찰을 종료 조건으로 쓸 때는 관찰 기록·manifest 적용·종료 검증을 별도 DB fence로 직렬화한다.