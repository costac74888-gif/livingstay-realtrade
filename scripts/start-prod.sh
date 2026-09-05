#!/bin/bash
set -euo pipefail

if [[ -z "${PROD_DATABASE_URL:-}" ]]; then
  echo "PROD_DATABASE_URL is required for the production app." >&2
  exit 1
fi

export DATABASE_URL="$PROD_DATABASE_URL"
export SERVE_MINIFIED_ASSETS=1
export SKIP_STARTUP_SCHEMA_INIT=1

python3 scripts/ensure_tourism_datalab_schema.py

exec gunicorn \
  --bind 0.0.0.0:5000 \
  --reuse-port \
  --timeout 120 \
  --workers 2 \
  --preload \
  --config gunicorn.conf.py \
  app:app