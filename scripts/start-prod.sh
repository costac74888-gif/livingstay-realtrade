#!/bin/bash
set -euo pipefail

if [ ! -x node_modules/.bin/terser ]; then
  npm ci --omit=dev --no-audit
fi
npm run build:frontend
export SERVE_MINIFIED_ASSETS=1

exec gunicorn \
  --bind 0.0.0.0:5000 \
  --reuse-port \
  --timeout 120 \
  --workers 2 \
  --preload \
  --config gunicorn.conf.py \
  app:app