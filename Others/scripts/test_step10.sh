#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[Step10] Running Step09 checks..."
bash "$REPO_ROOT/scripts/test_step09.sh"

echo "[Step10] Running analytics tests..."
cd "$REPO_ROOT/sat_platform"
pytest tests/test_analytics.py

echo "[Step10] All Step10 checks passed."

