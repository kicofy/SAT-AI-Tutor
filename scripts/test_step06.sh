#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

echo "[Step06] Running Step05 baseline checks..."
bash scripts/test_step05.sh

echo "[Step06] Running learning session tests..."
cd sat_platform
pytest tests/test_learning_sessions.py

echo "[Step06] All Step06 checks passed."

