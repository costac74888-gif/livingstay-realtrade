#!/bin/bash
set -e

# Install Python dependencies (idempotent — pip skips already-satisfied packages)
pip install -r requirements.txt

# 배포용 정적 JS를 재현 가능하게 생성한다.
npm ci --no-audit
# 이 검사는 app을 import하지만 DB DDL은 검증 대상이 아니다. 병합 후처리 중에는
# 기존 앱 워크플로가 아직 실행 중이므로 스키마 초기화를 건너뛰어 DDL lock 충돌을
# 피한다. 후처리 성공 뒤 워크플로 reconciliation이 앱을 재시작하며 새 스키마를 적용한다.
SKIP_STARTUP_SCHEMA_INIT=1 npm run test:frontend
