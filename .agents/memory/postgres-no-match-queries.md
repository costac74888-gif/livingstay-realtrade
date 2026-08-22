---
name: Postgres no-match queries
description: PostgreSQL에서 의도적으로 빈 결과를 만들 때 안전한 조건을 쓰는 규칙.
---

존재하지 않거나 삭제된 대상을 조회해 결과를 0건으로 제한할 때 문자열 NUL(`\x00`)을 센티널 값으로 넘기지 말고, 쿼리에 `FALSE` 조건을 추가한다.

**Why:** PostgreSQL TEXT 값에는 NUL 문자가 허용되지 않아, “절대 일치하지 않을 값”으로 보낸 NUL 바인딩이 쿼리를 500으로 실패시킨다.

**How to apply:** 선택적 ID를 먼저 조회한 뒤 대상이 없거나 유효한 이름·키가 없으면 파라미터에 문자열 센티널을 넣는 대신 `WHERE ... AND FALSE`가 되도록 조건을 추가한다. 이 경우 정상 JSON의 빈 목록/0개를 반환해야 한다.