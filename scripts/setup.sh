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
command -v python3 >/dev/null || { echo "python3 is required"; exit 1; }
command -v node >/dev/null || { echo "node is required"; exit 1; }
command -v npm >/dev/null || { echo "npm is required"; exit 1; }
command -v docker >/dev/null || { echo "docker is required (install Docker Desktop)"; exit 1; }

echo "==> Backend: creating venv and installing dependencies"
cd "$BACKEND_DIR"
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
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

Before deploying any agent, fill in real keys in backend/.env — at minimum
GROQ_API_KEY (manifesto expansion always runs on Groq). Everything else in
there is optional and only unlocks specific capabilities/providers.
EOF
