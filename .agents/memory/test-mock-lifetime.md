---
name: 전체 검사에서 모의 처리의 수명
description: unittest의 전역 patch.stopall이 다른 검사 모듈의 장기 fixture를 해제하는 위험
---

새 검사에서는 자신이 생성한 patch만 종료하고, 공용 전체 검사에서 `patch.stopall()`을 cleanup으로 쓰지 않는다.

**Why:** 개별 검사에서는 통과해도 전체 검사에서 다른 모듈의 장기 환경변수 fixture가 해제되어, 이후 수집기 검사들이 인증키 미설정으로 실패했다. 기준선 단독 실행과 전체 실행의 차이 때문에 중계 회귀로 오인하기 쉽다.

**How to apply:** `TestCase.enterContext`, `ExitStack`, 또는 각 patch 객체의 `stop`을 사용한다. 단독 실행과 전체 실행 결과가 다르면 제품 코드 변경에 앞서 전역 모의 처리의 수명을 확인한다.
