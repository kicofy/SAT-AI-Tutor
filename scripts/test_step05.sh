#!/usr/bin/env bash
set -euo pipefail

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_ROOT}/.." && pwd)"
SAT_DIR="${PROJECT_ROOT}/sat_platform"

cd "$SAT_DIR"

mkdir -p instance
DB_FILE="instance/sat_dev.db"

echo "[Step05] Resetting SQLite database at ${DB_FILE}"
rm -f "$DB_FILE"

echo "[Step05] Running migrations..."
FLASK_APP=app.py flask db upgrade

echo "[Step05] Seeding root/admin/student accounts..."
FLASK_APP=app.py flask seed-users

echo "[Step05] Running pytest suite for admin question CRUD..."
pytest tests/test_admin_questions.py

echo "[Step05] All checks passed."

