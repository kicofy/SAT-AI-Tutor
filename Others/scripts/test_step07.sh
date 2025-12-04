#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "[Step07] Running Step06 checks..."
bash "$REPO_ROOT/scripts/test_step06.sh"

echo "[Step07] Running AI explainer tests..."
cd "$REPO_ROOT/sat_platform"
pytest tests/test_ai_explainer.py

echo "[Step07] All Step07 checks passed."

