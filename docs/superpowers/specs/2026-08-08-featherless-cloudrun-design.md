# Design: Featherless AI + Google Cloud Run Migration

**Date:** 2026-08-08
**Status:** Approved
**Scope:** Replace Azure hosting with Google Cloud Run; add Featherless AI as LLM provider; remove Ollama/local GPU path

---

## Summary

Migrate Forge's deployment platform from Azure VMs to Google Cloud Run (serverless containers) and add Featherless AI as the primary LLM inference provider. This eliminates GPU instance management entirely — Featherless handles inference via API, Cloud Run handles container hosting with automatic scale-to-zero.

## Architecture

```
[React Frontend :5173]
       │
       │ REST API
       ▼
[FastAPI Backend :8000]  ──── Cloud Run (optional self-hosting)
       │
       ├── Featherless AI API (https://api.featherless.ai/v1)
       │     └── LLM inference (Llama, Mistral, Qwen, etc.)
       │
       ├── Google Cloud Run — Agent Services
       │     └── One Cloud Run service per deployed agent
       │         ├── /chat (proxied from backend)
       │         ├── /health
       │         ├── /custom-endpoints
       │         └── / (interactive chat webpage)
       │
       └── Google Cloud Run — MCP Pack Services
             ├── forge-mcp-research-pack (fetch, time, sequential_thinking, brave_search)
             ├── forge-mcp-dev-pack (filesystem, github)
             ├── forge-mcp-wolfram-alpha
             └── forge-mcp-playwright
```

## Design Decisions

### Why Featherless AI replaces Ollama/GPU instances
- Featherless is a serverless inference API — no GPU hardware to manage
- OpenAI-compatible endpoint — same integration pattern as Groq
- Supports function calling — MCP tool-use loops work unchanged
- Access to large models (70B+) without renting A100s
- Pay-per-token, not pay-per-hour-of-GPU

### Why Google Cloud Run replaces Azure VMs
- True serverless: scale to zero when idle, $0 cost
- No VM lifecycle management, no SSH tunneling, no Docker daemon forwarding
- Each agent is an isolated service with its own URL
- Auto-scales horizontally if an agent gets traffic
- Deploy = push Docker image + `gcloud run deploy`
- Cold start (~5-15s) is acceptable for chat UX (can add min-instances=1 for latency-sensitive agents)

### What gets removed
- `scripts/azure_deploy.sh` — deleted
- `backend/app/ollama_manager.py` — deleted (Featherless replaces local inference)
- SSH-based remote Docker in `mcp_manager.py` — replaced with Cloud Run service URLs
- `CAPABILITIES_DOCKER_HOST` / `CAPABILITIES_HOST` env vars — replaced with Cloud Run service URLs
- Ollama model options from `registry.py` — replaced with Featherless model catalog

---

## Part 1: Featherless AI Provider

### Model Registry

Add to `backend/app/registry.py`:

```python
# Featherless AI models (OpenAI-compatible API)
ModelOption(
    id="meta-llama/Meta-Llama-3.1-70B-Instruct",
    name="Llama 3.1 70B Instruct",
    provider="featherless",
    description="Meta's flagship open model, strong at reasoning and tool use",
),
ModelOption(
    id="meta-llama/Meta-Llama-3.1-8B-Instruct",
    name="Llama 3.1 8B Instruct",
    provider="featherless",
    description="Fast and capable smaller model",
),
ModelOption(
    id="mistralai/Mistral-Nemo-Instruct-2407",
    name="Mistral Nemo 12B",
    provider="featherless",
    description="Mistral's efficient mid-size model",
),
ModelOption(
    id="Qwen/Qwen2.5-72B-Instruct",
    name="Qwen 2.5 72B",
    provider="featherless",
    description="Alibaba's large multilingual model",
),
```

The full model list can be fetched dynamically from Featherless's `/v1/models` endpoint, but we'll ship with a curated static list and add dynamic fetching later if needed.

### Agent Runtime Integration

In `backend/agent_runtime/app.py`, add a `featherless` branch to the chat handler:

```python
elif provider == "featherless":
    from openai import OpenAI
    client = OpenAI(
        base_url="https://api.featherless.ai/v1",
        api_key=os.environ["FEATHERLESS_API_KEY"],
    )
    response = client.chat.completions.create(
        model=model_id,
        messages=messages,
        tools=tools if tools else NOT_GIVEN,
    )
    # Handle tool_calls the same way as the Groq path
```

This reuses the existing Groq/OpenAI-compatible function-calling loop — the only difference is `base_url` and the API key env var.

### Environment Variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `FEATHERLESS_API_KEY` | Agent container env | Per-agent key for inference calls |

The key is supplied per-agent via the wizard (same as Anthropic/Groq keys today). Add `"featherless": "FEATHERLESS_API_KEY"` to `docker_manager.PROVIDER_ENV_VAR`.

### Dependencies

Add `openai>=1.40.0` to `backend/agent_runtime/requirements.txt`.

---

## Part 2: Google Cloud Run Deployment

### Prerequisites

- Google Cloud project with billing enabled
- `gcloud` CLI authenticated
- Artifact Registry repository for Docker images
- Cloud Run API enabled

### Image Publishing

Docker images are built locally (or in CI) and pushed to Google Artifact Registry:

```
REGION-docker.pkg.dev/PROJECT_ID/forge/agent-runtime:latest
REGION-docker.pkg.dev/PROJECT_ID/forge/mcp-research-pack:latest
REGION-docker.pkg.dev/PROJECT_ID/forge/mcp-dev-pack:latest
REGION-docker.pkg.dev/PROJECT_ID/forge/mcp-wolfram-alpha:latest
REGION-docker.pkg.dev/PROJECT_ID/forge/mcp-playwright:latest
```

### New File: `backend/app/cloudrun_manager.py`

Replaces `docker_manager.py`'s deploy/stop/chat functions for production mode. Uses the Cloud Run Admin API (REST) or `google-cloud-run` Python SDK.

**Key functions:**

```python
def deploy_agent(agent, workspace_dir) -> tuple[str, str]:
    """Deploy an agent as a Cloud Run service.
    Returns (service_url, service_name)."""

def stop_agent(agent) -> None:
    """Delete the agent's Cloud Run service."""

def chat(agent, history: list[dict]) -> str:
    """POST to the agent's Cloud Run service URL /chat endpoint."""

def call_endpoint(agent, method, path, payload) -> dict:
    """Call a custom endpoint on the agent's Cloud Run service."""
```

**Deploy flow:**

1. Build the agent-runtime image with workspace baked in (or mount via Cloud Storage — TBD)
2. Push image to Artifact Registry
3. `gcloud run deploy forge-agent-{agent_id}` with:
   - `--image` pointing to the pushed image
   - `--set-env-vars` for MODEL_PROVIDER, MODEL_ID, FEATHERLESS_API_KEY, MCP URLs
   - `--min-instances=0` (scale to zero)
   - `--max-instances=3` (cap autoscale)
   - `--timeout=300` (5 min for long LLM responses)
   - `--allow-unauthenticated` (agent serves its own chat page)
   - `--port=8080`
4. Store the resulting service URL in the DB

**Workspace delivery:**

Two options (decision: bake into image):

- **Option A (chosen): Bake workspace into image at build time.** Each deploy does a `docker build` that COPYs the workspace into the image. Simple, self-contained, but requires a unique image per agent per deploy.
- **Option B: Mount from Cloud Storage.** Single shared image, workspace in a GCS bucket, loaded at container start. More complex but faster redeploys. Can add later as an optimization.

### MCP Pack Deployment

MCP packs deploy as persistent Cloud Run services (not per-agent):

```
forge-mcp-research-pack  → https://forge-mcp-research-pack-HASH-REGION.a.run.app
forge-mcp-dev-pack       → https://forge-mcp-dev-pack-HASH-REGION.a.run.app
forge-mcp-wolfram-alpha  → https://forge-mcp-wolfram-alpha-HASH-REGION.a.run.app
forge-mcp-playwright     → https://forge-mcp-playwright-HASH-REGION.a.run.app
```

Set `--min-instances=1` for MCP packs to avoid cold starts on tool calls (these are shared and cheap).

Agent containers reference MCP packs by their Cloud Run service URL instead of Docker container name.

### New File: `backend/app/mcp_manager_cloudrun.py`

Replaces `mcp_manager.py`'s `ensure_running()` for production:

```python
def ensure_running(mcp_server_key: str) -> str:
    """Return the Cloud Run URL for this MCP server.
    Deploys the service if it doesn't exist yet."""
    # Check if service exists via Cloud Run API
    # If not, deploy it
    # Return the service URL + SSE path
    return f"https://{service_name}-HASH-REGION.a.run.app{spec['sse_path']}"
```

### Environment Configuration

New env vars in `backend/.env`:

```bash
# Google Cloud Run deployment
GCP_PROJECT_ID=your-project-id
GCP_REGION=us-central1
GCP_ARTIFACT_REPO=forge
DEPLOY_MODE=local  # "local" (Docker) or "cloudrun"
```

`DEPLOY_MODE` controls which code path the build pipeline uses:
- `local` → existing `docker_manager.py` (dev, same as today)
- `cloudrun` → new `cloudrun_manager.py`

### Database Schema Changes

Add to the `Agent` model:

```python
cloudrun_service_name: Optional[str] = None  # e.g. "forge-agent-42"
cloudrun_service_url: Optional[str] = None   # e.g. "https://forge-agent-42-abc123-uc.a.run.app"
```

### Deploy Script: `scripts/cloudrun_deploy.sh`

Replaces `azure_deploy.sh`:

```bash
#!/usr/bin/env bash
# One-time setup: enable APIs, create Artifact Registry, deploy MCP packs,
# optionally deploy the backend itself to Cloud Run.

# 1. Enable Cloud Run + Artifact Registry APIs
# 2. Create Artifact Registry repo
# 3. Build and push all MCP pack images
# 4. Deploy MCP pack services (min-instances=1)
# 5. Output MCP service URLs for .env
# 6. Optionally deploy the backend as a Cloud Run service too
```

### Build Pipeline Changes

`backend/app/build_pipeline.py` step modifications:

| Step | Local mode (unchanged) | Cloud Run mode |
|------|----------------------|----------------|
| Validate configuration | Same | Same |
| Write agent files | Same | Same |
| Prepare local model | Ollama pull | Skip (Featherless is an API) |
| Start capability servers | Docker containers | Verify Cloud Run MCP services are live |
| Generate interactive webpage | Same | Same |
| Start container | `docker_manager.deploy()` | `cloudrun_manager.deploy_agent()` |
| Health check | localhost:port/health | service_url/health |
| Test chat | localhost:port/chat | service_url/chat |
| Test endpoints | localhost:port/path | service_url/path |

### Cost Model

| Component | Idle cost | Active cost |
|-----------|-----------|-------------|
| Agent services (scale-to-zero) | $0 | ~$0.00002/request + CPU-seconds |
| MCP packs (min-instances=1) | ~$5-10/mo total | Same + per-request |
| Featherless inference | $0 | Per-token (model-dependent) |
| Artifact Registry storage | ~$0.10/GB/mo | — |

**Total idle cost: ~$5-10/mo** (just the always-on MCP packs).

---

## Migration Path

1. Add Featherless AI provider (no breaking changes — additive)
2. Add `cloudrun_manager.py` + `mcp_manager_cloudrun.py` behind `DEPLOY_MODE=cloudrun` flag
3. Update build pipeline to branch on `DEPLOY_MODE`
4. Write `scripts/cloudrun_deploy.sh` for one-time infra setup
5. Delete `azure_deploy.sh`, `ollama_manager.py`, Ollama references
6. Update frontend to handle Cloud Run service URLs (agent page iframe)

Local Docker development continues to work unchanged (`DEPLOY_MODE=local`).

---

## Open Questions (resolved)

- ~~Workspace delivery: bake into image vs. GCS mount~~ → Bake into image (simpler; optimize later)
- ~~Cold start mitigation~~ → Acceptable for chat; add `--min-instances=1` flag in UI for latency-sensitive agents later
- ~~Authentication~~ → `--allow-unauthenticated` for now; can add IAM auth layer later

---

## Files Created/Modified

**New files:**
- `backend/app/cloudrun_manager.py` — Cloud Run deploy/stop/chat/endpoint calls
- `backend/app/mcp_manager_cloudrun.py` — MCP pack deployment on Cloud Run
- `scripts/cloudrun_deploy.sh` — One-time infra setup script

**Modified files:**
- `backend/app/registry.py` — Add Featherless provider + models
- `backend/app/docker_manager.py` — Add `featherless` to PROVIDER_ENV_VAR
- `backend/app/build_pipeline.py` — Branch on DEPLOY_MODE for each step
- `backend/agent_runtime/app.py` — Add Featherless chat handler
- `backend/agent_runtime/requirements.txt` — Add `openai` package
- `backend/agent_runtime/Dockerfile` — No GPU deps needed (stays slim)
- `backend/.env.example` — Add GCP + Featherless vars
- `backend/app/models.py` — Add cloudrun_service_name/url fields
- `backend/app/schemas.py` — Expose new fields
- `frontend/src/pages/AgentPage.tsx` — Use service URL for iframe when in cloudrun mode

**Deleted files:**
- `scripts/azure_deploy.sh`
- `backend/app/ollama_manager.py`
