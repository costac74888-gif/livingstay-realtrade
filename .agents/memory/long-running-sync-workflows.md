---
name: Long-running sync workflow execution
description: Replit 셸 호출과 장기 데이터 수집 프로세스의 생명주기 차이를 다룬다.
---

장기 수집 작업은 `ShellExec`/코드 실행 샌드박스에서 분리 프로세스로 띄우지 말고 Replit 워크플로로 실행한다.

**Why:** `start_new_session=True`로 실행해도 셸 호출이 끝난 직후 자식 프로세스가 사라질 수 있어, 상태 행만 `running`으로 남고 실제 체크포인트가 진행하지 않는 고아 상태가 발생한다.

**How to apply:** 수집·백필처럼 수 분 이상 걸리는 작업은 기존 전용 워크플로를 사용하거나, 안전한 빈 워크플로 슬롯이 있을 때 콘솔 워크플로로 구성한다. 시작 뒤에는 워크플로 로그, DB 체크포인트, 상태 하트비트 세 가지를 함께 확인한다.