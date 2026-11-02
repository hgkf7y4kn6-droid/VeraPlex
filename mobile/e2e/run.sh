#!/usr/bin/env bash
# Boots the real backend on a throwaway SQLite DB, seeds it, and runs the client sync engine against it.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PY="${PYTHON:-python3}"
DB="$(mktemp -d)/e2e.db"
export VERAPLEX_DATABASE_URL="sqlite:///$DB"
export VERAPLEX_SUPABASE_JWT_SECRET="e2e-secret-e2e-secret-e2e-secret-123456"
cd "$ROOT/backend"
export PYTHONPATH="$ROOT/backend"
IDS="$($PY scripts/seed_dev.py)"
$PY -m uvicorn app.main:app --port 8765 --log-level warning &
PID=$!
trap 'kill $PID 2>/dev/null || true' EXIT
for _ in $(seq 1 40); do curl -sf http://127.0.0.1:8765/healthz >/dev/null && break; sleep 0.25; done
cd "$ROOT/mobile"
export NO_PROXY=127.0.0.1,localhost no_proxy=127.0.0.1,localhost
E2E_API_URL=http://127.0.0.1:8765 E2E_SECRET="$VERAPLEX_SUPABASE_JWT_SECRET" E2E_IDS="$IDS" npx tsx --test e2e/e2e.test.ts
