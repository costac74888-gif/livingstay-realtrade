---
name: Browser action completion
description: Await completed responses and stable controls before asserting asynchronous UI feedback.
---

비동기 작업 검사는 feedback가 보인다는 조건만으로 완료를 판단하지 않는다.
작업 응답과 컨트롤의 대기 상태를 확인한 뒤 결과·인증·권한 상태를 검증한다.

**Why:** 처리중 안내도 같은 feedback 영역을 사용하므로, 화면이 보인 직후
결과 assertion을 실행하면 요청이 끝나기 전에 간헐적으로 실패한다.

**How to apply:** 로그인 실패·저장·재시도 검사에서 실제 응답을 기다리고
해당 작업의 busy 상태가 끝났는지 확인한다. assertion을 제거하거나 실패를
무시하지 말고 완료 조건을 강화한다.
