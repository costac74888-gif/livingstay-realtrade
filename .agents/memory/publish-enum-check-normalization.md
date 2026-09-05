---
name: Publish의 enum CHECK 변환
description: PostgreSQL enum형 CHECK 제약을 Replit Publish가 잘못 변환할 수 있는 환경 특이사항
---

개발 DB에 나중에 추가한 `CHECK (value IN (...))` 제약은 PostgreSQL introspection에서 `ANY(ARRAY)` 형태로 정규화될 수 있다. Publish 스키마 diff가 이를 standalone `ADD CONSTRAINT`로 다시 만들 때 괄호 수를 잘못 생성하는 경우가 있으므로, 계산된 게시 SQL을 확인해야 한다.

**Why:** 정상 제약이 게시 단계에서 닫는 괄호가 하나 많은 SQL로 생성되어 production migration validation이 실패했다.

**How to apply:** 새 enum형 상태 컬럼을 배포할 때 게시 전 schema diff의 `ADD CONSTRAINT` 문법을 확인한다. 문제가 재현되면 애플리케이션 allowlist 검증으로 무결성을 유지하고 해당 standalone CHECK는 개발 스키마에서 제거한다.