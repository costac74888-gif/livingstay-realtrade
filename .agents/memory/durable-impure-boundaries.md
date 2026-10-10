---
name: Persisted impure boundaries
description: Durable notebook functions can retain a stale sandbox transformation across runtime changes.
---

노트북에 남아 있는 impure 함수가 typeof function이라고 해서 다음 세션에서도
실행 가능한 것은 아니다. sandbox runtime이 달라지면 내부 변환 wrapper가 더 이상
제공하지 않는 실행 함수를 참조할 수 있다.

**Why:** 기존 함수 호출은 executeJs 부재로 실패했지만 같은 작업을 새로운
`"use impure"` 경계에서 실행하자 정상 동작했다. 연결 인증·API 자체 실패가 아니었다.

**How to apply:** 이런 실패를 인증 만료로 오판하거나 재연결/비밀값 조회로 우회하지
말고, 관련 skill의 현재 callback 규칙으로 새 impure 경계를 만든다. 원격 쓰기를
재시도할 때는 이미 반영된 object/ref를 읽고 멱등성·해시·비강제 갱신을 유지한다.
