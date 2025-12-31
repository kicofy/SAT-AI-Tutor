#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
BACKEND_DIR="${REPO_ROOT}/sat_platform"
FRONTEND_DIR="${REPO_ROOT}/frontend"
ENV_FILE="${BACKEND_DIR}/.env"
FRONTEND_ENV="${FRONTEND_DIR}/.env.local"

prompt() {
  local var_name="$1" prompt_text="$2" default="${3:-}"
  local value=""
  if [[ -n "${default}" ]]; then
    read -r -p "${prompt_text} [${default}]: " value || true
  else
    read -r -p "${prompt_text}: " value || true
  fi
  if [[ -z "${value}" && -n "${default}" ]]; then
    value="${default}"
  fi
  printf -v "${var_name}" '%s' "${value}"
}

confirm() {
  local prompt_text="$1"
  read -r -p "${prompt_text} [y/N]: " reply || true
  [[ "${reply}" =~ ^[Yy]$ ]]
}

echo "== SAT AI Tutor one-click initializer =="
echo "Repo root: ${REPO_ROOT}"

# Ensure python
if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 not found. Please install Python 3.10+." >&2
  exit 1
fi

# Virtualenv
if [[ ! -d "${REPO_ROOT}/.venv" ]]; then
  if confirm "Create virtualenv at .venv?"; then
    python3 -m venv "${REPO_ROOT}/.venv"
  fi
fi
if [[ -d "${REPO_ROOT}/.venv" ]]; then
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.venv/bin/activate"
fi

# Install backend deps
if confirm "Install backend dependencies (pip install -r sat_platform/requirements.txt)?"; then
  pip install --upgrade pip
  pip install -r "${BACKEND_DIR}/requirements.txt"
fi

# Gather env values
echo
echo "== Backend environment (.env) =="
prompt ROOT_ADMIN_USER "Root admin username" "ha22y"
prompt ROOT_ADMIN_PASS "Root admin password" "Kicofy5438"
prompt ROOT_ADMIN_EMAIL "Root admin email" "ha22y@example.com"
prompt JWT_SECRET "JWT secret (random string)" "$(openssl rand -hex 16 2>/dev/null || echo 'change-me')"
prompt DATABASE_URL "Database URL" "sqlite:///sat_dev.db"
prompt CORS_ORIGINS "CORS origins (comma-separated)" "http://127.0.0.1:3000"
prompt OPENAI_API_KEY "OpenAI API Key" ""
prompt AI_EXPLAINER_MODEL "AI explainer model" "gpt-5.2"
prompt AI_PARSER_MODEL "AI parser model" "gpt-5.2"
prompt AI_PDF_NORMALIZE_MODEL "AI PDF normalize model" "gpt-5.2"
prompt MAIL_SERVER "Mail server (Zoho example smtppro.zoho.com)" ""
prompt MAIL_PORT "Mail port" "587"
prompt MAIL_USERNAME "Mail username" ""
prompt MAIL_PASSWORD "Mail password/app password" ""
prompt MAIL_SENDER "Mail sender name" "SAT AI Tutor"

cat > "${ENV_FILE}" <<EOF
FLASK_CONFIG=dev
DATABASE_URL=${DATABASE_URL}
JWT_SECRET_KEY=${JWT_SECRET}
CORS_ORIGINS=${CORS_ORIGINS}

ROOT_ADMIN_USERNAME=${ROOT_ADMIN_USER}
ROOT_ADMIN_PASSWORD=${ROOT_ADMIN_PASS}
ROOT_ADMIN_EMAIL=${ROOT_ADMIN_EMAIL}

OPENAI_API_KEY=${OPENAI_API_KEY}
AI_EXPLAINER_MODEL=${AI_EXPLAINER_MODEL}
AI_PARSER_MODEL=${AI_PARSER_MODEL}
AI_PDF_NORMALIZE_MODEL=${AI_PDF_NORMALIZE_MODEL}

MAIL_SERVER=${MAIL_SERVER}
MAIL_PORT=${MAIL_PORT}
MAIL_USE_TLS=true
MAIL_USE_SSL=false
MAIL_USERNAME=${MAIL_USERNAME}
MAIL_PASSWORD=${MAIL_PASSWORD}
MAIL_DEFAULT_SENDER="${MAIL_SENDER} <${MAIL_USERNAME}>"
MAIL_DEFAULT_NAME=${MAIL_SENDER}
MAIL_REPLY_TO=${MAIL_USERNAME}
MAIL_IMAP_SERVER=imappro.zoho.com
MAIL_IMAP_PORT=993
MAIL_IMAP_USE_SSL=true
EOF
echo "Wrote backend env to ${ENV_FILE}"

# Frontend env
echo
echo "== Frontend environment (.env.local) =="
prompt API_BASE "API base URL for frontend" "http://127.0.0.1:5080"
cat > "${FRONTEND_ENV}" <<EOF
NEXT_PUBLIC_API_BASE_URL=${API_BASE}
EOF
echo "Wrote frontend env to ${FRONTEND_ENV}"

# Run migrations
if confirm "Run flask db upgrade now?"; then
  (cd "${BACKEND_DIR}" && FLASK_APP=app flask db upgrade)
fi

echo
echo "Done. Next steps:"
echo "- Activate venv: source .venv/bin/activate"
echo "- Start backend: cd sat_platform && flask --app app run"
echo "- Start frontend: cd frontend && npm run dev"

