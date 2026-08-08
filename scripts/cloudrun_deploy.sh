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
