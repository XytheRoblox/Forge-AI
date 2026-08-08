### Task 6: Deployment Scripts and Cleanup

**Files:**
- Create: `scripts/cloudrun_deploy.sh`
- Create: `scripts/push_images.sh`
- Delete: `scripts/azure_deploy.sh`
- Delete: `backend/app/ollama_manager.py`
- Modify: `backend/app/build_pipeline.py:11` (remove ollama import)
- Modify: `backend/.env.example`

**Interfaces:**
- Consumes: GCP project credentials, Docker images in `backend/agent_runtime/` and `backend/mcp_servers/`
- Produces: Shell scripts for one-time GCP setup and image publishing

- [ ] **Step 1: Create push_images.sh**

Create `scripts/push_images.sh`:

```bash
#!/usr/bin/env bash
# Builds all Docker images and pushes them to Google Artifact Registry.
# Run this after any change to agent_runtime/ or mcp_servers/.
#
# Prerequisites: `gcloud auth configure-docker REGION-docker.pkg.dev` already done.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
: "${GCP_REGION:=us-central1}"
: "${GCP_ARTIFACT_REPO:=forge}"

REGISTRY="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${GCP_ARTIFACT_REPO}"

echo "==> Building and pushing agent-runtime"
docker build -t "${REGISTRY}/agent-runtime:latest" "$ROOT_DIR/backend/agent_runtime"
docker push "${REGISTRY}/agent-runtime:latest"

echo "==> Building and pushing MCP packs"
for pack in wolframalpha playwright research_pack dev_pack; do
    image_name="forge-mcp-${pack//_/-}"
    docker build -t "${REGISTRY}/${image_name}:latest" "$ROOT_DIR/backend/mcp_servers/$pack"
    docker push "${REGISTRY}/${image_name}:latest"
done

echo "==> All images pushed to ${REGISTRY}"
```

- [ ] **Step 2: Create cloudrun_deploy.sh**

Create `scripts/cloudrun_deploy.sh`:

```bash
#!/usr/bin/env bash
# One-time Google Cloud Run setup: enables APIs, creates Artifact Registry,
# deploys the shared MCP pack services, and outputs env vars for .env.
#
# Prerequisites: `gcloud auth login` done, billing enabled on project.
set -euo pipefail

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID}"
: "${GCP_REGION:=us-central1}"
: "${GCP_ARTIFACT_REPO:=forge}"

REGISTRY="${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${GCP_ARTIFACT_REPO}"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> Enabling APIs"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com --project="$GCP_PROJECT_ID"

echo "==> Creating Artifact Registry repo (if needed)"
gcloud artifacts repositories describe "$GCP_ARTIFACT_REPO" \
  --location="$GCP_REGION" --project="$GCP_PROJECT_ID" 2>/dev/null || \
gcloud artifacts repositories create "$GCP_ARTIFACT_REPO" \
  --repository-format=docker --location="$GCP_REGION" --project="$GCP_PROJECT_ID"

echo "==> Configuring Docker auth"
gcloud auth configure-docker "${GCP_REGION}-docker.pkg.dev" --quiet

echo "==> Building and pushing images"
"$ROOT_DIR/scripts/push_images.sh"

echo "==> Deploying MCP pack services (min-instances=1)"
for pack in forge-mcp-research-pack forge-mcp-dev-pack forge-mcp-wolfram-alpha forge-mcp-playwright; do
    echo "    Deploying $pack..."
    port=8000
    [ "$pack" = "forge-mcp-playwright" ] && port=8931
    gcloud run deploy "$pack" \
      --image="${REGISTRY}/${pack}:latest" \
      --region="$GCP_REGION" \
      --project="$GCP_PROJECT_ID" \
      --port="$port" \
      --min-instances=1 \
      --max-instances=2 \
      --timeout=60 \
      --allow-unauthenticated \
      --cpu=1 \
      --memory=512Mi \
      --quiet
done

echo ""
echo "==> Done. Add these to your backend/.env:"
echo ""
echo "  GCP_PROJECT_ID=$GCP_PROJECT_ID"
echo "  GCP_REGION=$GCP_REGION"
echo "  GCP_ARTIFACT_REPO=$GCP_ARTIFACT_REPO"
echo "  DEPLOY_MODE=cloudrun"
echo ""
echo "MCP service URLs:"
for pack in forge-mcp-research-pack forge-mcp-dev-pack forge-mcp-wolfram-alpha forge-mcp-playwright; do
    url=$(gcloud run services describe "$pack" --region="$GCP_REGION" --project="$GCP_PROJECT_ID" --format="value(status.url)" 2>/dev/null || echo "(not deployed)")
    echo "  $pack: $url"
done
```

- [ ] **Step 3: Make scripts executable**

```bash
chmod +x scripts/cloudrun_deploy.sh scripts/push_images.sh
```

- [ ] **Step 4: Delete azure_deploy.sh**

```bash
rm scripts/azure_deploy.sh
```

- [ ] **Step 5: Delete ollama_manager.py and remove its import**

```bash
rm backend/app/ollama_manager.py
```

In `backend/app/build_pipeline.py`, change the import line:

```python
from app import docker_manager, mcp_manager, ollama_manager, webpage_gen, workspace
```

To:

```python
from app import docker_manager, mcp_manager, webpage_gen, workspace
```

Guard the ollama usage in the "Prepare local model" step with a conditional import:

```python
        if agent.model_provider == "ollama" and DEPLOY_MODE == "local":
            from app import ollama_manager
            step.detail = f"Pulling {agent.model_id!r}…"
            ...
```

Also in `backend/app/docker_manager.py`, the Ollama reference at line 146 needs guarding:

```python
    if agent.model_provider == "ollama":
        from app import ollama_manager

        internal_url, _ = ollama_manager.ensure_running()
        env["OLLAMA_URL"] = internal_url
```

This import is already inline (lazy), so it only runs when an Ollama agent deploys locally — which still works. No change needed to docker_manager.py.

- [ ] **Step 6: Update .env.example with full GCP section**

Append to `backend/.env.example`:

```bash

# Google Cloud Run deployment (set DEPLOY_MODE=cloudrun to use)
GCP_PROJECT_ID=
GCP_REGION=us-central1
GCP_ARTIFACT_REPO=forge
DEPLOY_MODE=local
```

- [ ] **Step 7: Commit**

```bash
git add scripts/cloudrun_deploy.sh scripts/push_images.sh backend/app/build_pipeline.py backend/.env.example
git rm scripts/azure_deploy.sh backend/app/ollama_manager.py
git commit -m "feat: add Cloud Run deploy scripts, remove Azure and Ollama"
```

