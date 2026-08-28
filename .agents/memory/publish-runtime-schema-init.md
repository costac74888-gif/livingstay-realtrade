---
name: Publish 런타임 스키마 초기화
description: Publish 스키마 반영과 app_meta 버전이 어긋날 때 Promote 시작이 DDL 대기로 실패하는 문제를 방지하는 원칙
---

운영 Publish 런타임은 앱 시작 시 `init_db()`를 실행하지 않는다. Publish가 Promote 전에 스키마 차이를 적용하며, 운영 시작 스크립트는 명시적인 환경 플래그로 부팅 DDL을 건너뛴다. 개발 환경의 자동 초기화는 유지한다.

**Why:** Publish가 실제 제약·인덱스를 정상 반영해도 애플리케이션 데이터인 `app_meta.schema_version`은 이전 값일 수 있다. 이때 preload 단계에서 전체 DDL을 다시 실행하면 대형 테이블 잠금으로 포트를 열기 전에 Promote 제한 시간이 끝난다.

**How to apply:** 새 스키마는 Publish의 스키마 비교·반영 흐름으로 배포한다. 운영 실행 명령에서 부팅 DDL 생략 플래그를 유지하고, 프런트 자산 생성처럼 포트 개방 전 시간이 걸리는 작업은 런타임이 아니라 deployment Build 단계에 둔다.