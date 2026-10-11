#!/bin/bash
set -e

# Install Python dependencies (idempotent — pip skips already-satisfied packages)
pip install -r requirements.txt

# 배포용 정적 JS를 재현 가능하게 생성한다.
npm ci --no-audit
# 앱 워크플로는 reconciliation 전에는 중지되어 있을 수 있다.
# 운영 연결·알림을 차단한 소유 임시 DB/HTTP에서 기존 검사를 그대로 실행한다.
python scripts/post_merge_checks.py
