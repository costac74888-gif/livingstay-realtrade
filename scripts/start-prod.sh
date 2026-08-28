#!/bin/bash
set -euo pipefail

export SERVE_MINIFIED_ASSETS=1
export SKIP_STARTUP_SCHEMA_INIT=1

exec gunicorn \
  --bind 0.0.0.0:5000 \
  --reuse-port \
  --timeout 120 \
  --workers 2 \
  --preload \
  --config gunicorn.conf.py \
  app:app