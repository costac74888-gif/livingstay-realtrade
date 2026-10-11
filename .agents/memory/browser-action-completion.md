---
name: Browser action completion
description: Await completed responses and stable controls before asserting asynchronous UI feedback.
---

비동기 작업 검사는 feedback가 보인다는 조건만으로 완료를 판단하지 않는다.
작업 응답과 컨트롤의 대기 상태를 확인한 뒤 결과·인증·권한 상태를 검증한다.

**Why:** 처리중 안내도 같은 feedback 영역을 사용하므로, 화면이 보인 직후
결과 assertion을 실행하면 요청이 끝나기 전에 간헐적으로 실패한다.
로그인 버튼 노출도 초기 익명 화면과 공통 인증 조회가 끝났음을 보장하지
않는다. 인증 응답 경합 방어와 검사 시작 시점의 준비 조건은 별개로 확인한다.

**How to apply:** 로그인 실패·저장·재시도 검사에서 실제 응답을 기다리고
해당 작업의 busy 상태가 끝났는지 확인한다. assertion을 제거하거나 실패를
무시하지 말고 완료 조건을 강화한다.

전체 리소스의 load 이벤트와 업무 화면 준비 상태는 구분한다.

**Why:** 채팅 새로고침은 문서 탐색 후에도 load 대기에서 간헐적으로 멈췄다.
저장된 메시지와 API 준비 상태를 확인하는 것은 별도의 완료 증거다.

**How to apply:** 비필수 리소스의 load에 기대지 않고 DOMContentLoaded 후
실제 응답·ready 상태·저장 결과를 기다린다. 단순 대기 단축으로 assertion을 우회하지 않는다.
