#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[Step08] Running Step07 checks..."
bash "$REPO_ROOT/scripts/test_step07.sh"

echo "[Step08] Running adaptive engine tests..."
cd "$REPO_ROOT/sat_platform"
pytest tests/test_adaptive_engine.py

echo "[Step08] All Step08 checks passed."

