#!/bin/bash
set -e

# Install Python dependencies (idempotent — pip skips already-satisfied packages)
pip install -r requirements.txt

# 배포용 정적 JS를 재현 가능하게 생성한다.
npm ci --no-audit
npm run test:frontend
