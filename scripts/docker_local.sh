#!/usr/bin/env bash
# Builds every image the app needs to deploy agents and capabilities
# LOCALLY via Docker Desktop, and creates the shared network they all sit
# on. Run this once after cloning (setup.sh already calls it), and again
# any time you change a Dockerfile under backend/ and want the prebuilt
# image to reflect it before the next agent build — the app itself always
# rebuilds on deploy anyway, so this is purely about avoiding that first
# slow build the moment you actually use the app.
#
# This intentionally only covers local Docker Desktop. Azure deployment
# (pushing these to a registry, running them there) is a separate concern —
# scripts/docker_azure.sh, not written yet — kept apart on purpose so
# local dev never depends on Azure being configured at all.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCP_DIR="$ROOT_DIR/backend/mcp_servers"

command -v docker >/dev/null || { echo "docker is required (install Docker Desktop)"; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker daemon isn't reachable — start Docker Desktop first"; exit 1; }

NETWORK_NAME="forge-net"
echo "==> Ensuring shared Docker network '$NETWORK_NAME'"
docker network inspect "$NETWORK_NAME" >/dev/null 2>&1 || docker network create "$NETWORK_NAME" >/dev/null

# Keep these tags/paths in sync with the Python source of truth:
# backend/app/docker_manager.py (IMAGE_TAG), backend/app/mcp_manager.py
# (MCP_SERVER_SPECS), backend/app/ollama_manager.py (IMAGE) — if one of
# those changes, mirror it here too.
echo "==> Building agent runtime image"
docker build -t zovo-agent-runtime:latest "$ROOT_DIR/backend/agent_runtime"

echo "==> Building capability images"
echo "  - wolfram_alpha"
docker build -t forge-mcp-wolfram-alpha:latest "$MCP_DIR/wolframalpha"
echo "  - playwright (browser_use)"
docker build -t forge-mcp-playwright:latest "$MCP_DIR/playwright"
echo "  - research_pack (fetch, time, sequential_thinking, web_search)"
docker build -t forge-mcp-research-pack:latest "$MCP_DIR/research_pack"
echo "  - dev_pack (filesystem, github)"
docker build -t forge-mcp-dev-pack:latest "$MCP_DIR/dev_pack"

echo "==> Pulling local-model image (Ollama) — only needed if you deploy an agent with an Ollama model"
docker pull ollama/ollama:latest >/dev/null

echo "==> All local images ready:"
docker images --format "{{.Repository}}:{{.Tag}}" | grep -E "^(zovo-agent-runtime:|forge-mcp-|ollama/ollama:)" | sort -u | sed 's/^/  /'
