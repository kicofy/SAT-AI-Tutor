#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[Step11] Running Step10 checks..."
bash "$REPO_ROOT/scripts/test_step10.sh"

echo "[Step11] Running question import tests..."
cd "$REPO_ROOT/sat_platform"
pytest tests/test_question_imports.py

echo "[Step11] All Step11 checks passed."

