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
