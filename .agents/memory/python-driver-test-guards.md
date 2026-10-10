---
name: Python·DB 드라이버 검사 경계
description: 고수준 connect와 네이티브 드라이버의 인수 차이, sitecustomize의 fail-open 위험
---

Python 검사 가드는 네이티브 DB 드라이버까지 감싸되 고수준 연결 함수와 C 드라이버의 인수 계약을 동일하게 취급하지 않는다. psycopg2의 cursor_factory는 DSN 항목이 아니며 C 연결 함수로 그대로 넘기지 않는다.

**Why:** 여러 경계 접근을 시도하면서 고수준 함수에서 유효한 인수가 DSN 파서와 네이티브 호출에서는 거부되는 것을 확인했다. 잘못된 가드의 오류를 앱 스키마 오류로 해석하면 원인 진단이 어긋난다.

**How to apply:** 연결 옵션과 Python factory를 분리하고 실제 로컬 PostgreSQL 연결로 검사한다. 연결 가드 설치 실패를 실제 DB 접근으로 폴백하지 않는다.

sitecustomize에서 일반 Exception을 던지는 것은 실행 중단 보장이 아니다. Python은 오류를 출력한 뒤 애플리케이션을 계속 실행할 수 있다.

**Why:** 격리 capability가 없을 때 가드가 무시되면 검사 코드가 정상 환경의 DB 설정으로 진입할 위험이 있다.

**How to apply:** capability 검증 실패는 interpreter를 즉시 종료시키고, 후속 코드가 실행되지 않는 별도 subprocess 검사를 유지한다.
