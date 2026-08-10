#!/usr/bin/env bash
# Provisions this project for local development: backend venv + deps,
# frontend deps, a starter .env, then hands off to docker_local.sh to build
# every image the app deploys agents/capabilities into.
#
# Azure deployment is intentionally out of scope here — this script only
# covers running everything locally via Docker Desktop. A separate
# scripts/docker_azure.sh (not written yet) will own pushing these same
# images to a registry and deploying them there, once that work starts.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"

echo "==> Checking prerequisites"
# .python-version pins the interpreter this project is developed against
# (currently 3.11.x). A bare `python3` is whatever happens to be first on
# PATH — on macOS that's often the system 3.9, which can't install these
# requirements — so resolve the pinned minor version explicitly and only
# fall back to `python3` when it already satisfies the pin.
PYTHON_PIN="$(cut -d. -f1,2 < "$ROOT_DIR/.python-version")"
if command -v "python$PYTHON_PIN" >/dev/null; then
  PYTHON_BIN="python$PYTHON_PIN"
elif command -v python3 >/dev/null && python3 -c "import sys; sys.exit(0 if '.'.join(map(str, sys.version_info[:2])) == '$PYTHON_PIN' else 1)"; then
  PYTHON_BIN=python3
else
  echo "python$PYTHON_PIN is required (see .python-version); install it, e.g. 'brew install python@$PYTHON_PIN'"
  exit 1
fi
echo "  using $PYTHON_BIN ($("$PYTHON_BIN" --version))"
command -v node >/dev/null || { echo "node is required"; exit 1; }
command -v npm >/dev/null || { echo "npm is required"; exit 1; }
command -v docker >/dev/null || { echo "docker is required (install Docker Desktop)"; exit 1; }

echo "==> Backend: creating venv and installing dependencies"
cd "$BACKEND_DIR"
if [ ! -d ".venv" ]; then
  "$PYTHON_BIN" -m venv .venv
fi
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt

if [ ! -f ".env" ]; then
  echo "==> Creating backend/.env from .env.example (fill in your real keys before deploying agents)"
  cp .env.example .env
else
  echo "==> backend/.env already exists, leaving it alone"
fi

echo "==> Frontend: installing dependencies"
cd "$FRONTEND_DIR"
npm install --silent

echo "==> Provisioning local Docker images (agent runtime + MCP capability packs)"
"$ROOT_DIR/scripts/docker_local.sh"

cat <<'EOF'

==> Done. To run the app:

  Backend:  cd backend && .venv/bin/uvicorn app.main:app --port 8000
  Frontend: cd frontend && npm run dev
  Tests:    cd backend && .venv/bin/python -m pytest tests

Before deploying any agent, fill in real keys in backend/.env — at minimum
GROQ_API_KEY (manifesto expansion always runs on Groq). Everything else in
there is optional and only unlocks specific capabilities/providers.
EOF
