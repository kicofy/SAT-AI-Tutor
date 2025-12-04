#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[Step09] Running Step08 checks..."
bash "$REPO_ROOT/scripts/test_step08.sh"

echo "[Step09] Running learning plan tests..."
cd "$REPO_ROOT/sat_platform"
pytest tests/test_learning_plan.py

echo "[Step09] All Step09 checks passed."

