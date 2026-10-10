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

큰 JSON 전송은 파일 원문 크기뿐 아니라 반환값의 JSON escaping 비용과 노트북
누적 메모리도 고려한다. 필요하면 UTF-8 문자 경계에서 작은 조각으로 나누고
읽은 원문·응답을 오래 유지하지 않는다.

**Why:** 1MB 미만 원문도 반환 직렬화 한도를 넘었고, 원격 쓰기가 끝난 뒤
32MiB 누적 메모리 초과로 노트북이 초기화되면서 호출은 failed처럼 표시됐다.

**How to apply:** 이런 오류 뒤에는 쓰기가 실패했다고 가정해 다시 보내지 말고
새 경계에서 원격 결과를 독립 조회해 먼저 실제 반영 여부를 확인한다.
