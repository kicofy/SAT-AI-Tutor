#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[Step12] Running Step11 checks..."
bash "$REPO_ROOT/scripts/test_step11.sh"

echo "[Step12] Running lint checks..."
cd "$REPO_ROOT"
python3 -m pip install --quiet ruff black isort >/dev/null
ruff check sat_platform
black --check sat_platform
isort --check-only sat_platform

echo "[Step12] Running hardening tests..."
cd "$REPO_ROOT/sat_platform"
pytest tests/test_metrics.py

echo "[Step12] All Step12 checks passed."

