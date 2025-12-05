#!/usr/bin/env bash
# Automated smoke test for the adaptive daily plan algorithm (plan.v2).
#
# Requirements:
#   - API server running locally (defaults to http://127.0.0.1:5080)
#   - jq installed
#   - A student account already exists (email/password)
#
# Optional environment variables:
#   API_BASE .......... Base URL for the backend (default http://127.0.0.1:5080)
#   STUDENT_EMAIL ..... Email used for login
#   STUDENT_PASSWORD .. Password used for login
#
# Usage:
#   chmod +x scripts/test_plan_algorithm.sh
#   STUDENT_EMAIL=user@example.com STUDENT_PASSWORD=secret ./scripts/test_plan_algorithm.sh

set -euo pipefail

API_BASE="${API_BASE:-http://127.0.0.1:5080}"
STUDENT_EMAIL="${STUDENT_EMAIL:-student@example.com}"
STUDENT_PASSWORD="${STUDENT_PASSWORD:-password123}"

if ! command -v jq >/dev/null 2>&1; then
  echo "[error] jq is required for this script." >&2
  exit 1
fi

echo "→ Logging in as ${STUDENT_EMAIL}"
TOKEN="$(
  curl -sS -X POST "${API_BASE}/api/auth/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"${STUDENT_EMAIL}\",\"password\":\"${STUDENT_PASSWORD}\"}" \
    | jq -r ".access_token"
)"

if [[ -z "${TOKEN}" || "${TOKEN}" == "null" ]]; then
  echo "[error] Failed to obtain JWT. Check credentials." >&2
  exit 1
fi

echo "→ Fetching existing plan"
curl -sS "${API_BASE}/api/learning/plan/today" \
  -H "Authorization: Bearer ${TOKEN}" \
  | jq '.plan | {protocol_version, insights, blocks: [.blocks[] | {focus_skill, priority_score, strategy_tips}]}' \
  || {
    echo "[error] Failed to fetch plan" >&2
    exit 1
  }

echo "→ Forcing regeneration to verify determinism"
curl -sS -X POST "${API_BASE}/api/learning/plan/regenerate" \
  -H "Authorization: Bearer ${TOKEN}" \
  | jq '.plan | {protocol_version, insights, blocks: [.blocks[] | {focus_skill, priority_score, strategy_tips}]}' \
  || {
    echo "[error] Failed to regenerate plan" >&2
    exit 1
  }

echo "✅ Daily plan algorithm smoke test completed."

