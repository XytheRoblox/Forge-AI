### Task 5 Report: Deploy Mode Branching and service_url Integration

**Status: DONE** — commit `e2dd4d3`

---

#### Changes Made

**backend/app/models.py**
- Added `service_url: Optional[str] = None` and `cloudrun_service_name: Optional[str] = None` after `container_port` on the `Agent` SQLModel.

**backend/app/schemas.py**
- Added matching `service_url: Optional[str]` and `cloudrun_service_name: Optional[str]` fields to `AgentRead` (the API response schema).

**backend/app/build_pipeline.py**
- Added `import os` and `DEPLOY_MODE = os.environ.get("DEPLOY_MODE", "local")` after all imports (default is `"local"`, no breaking change).
- "Prepare local model" step now only runs `ollama_manager.ensure_model_pulled()` when `DEPLOY_MODE == "local" AND provider == "ollama"`; otherwise skips with "Not needed (using API-based inference)."
- "Start container" step branches: cloudrun → lazy-imports `cloudrun_manager` and calls `deploy_agent(agent, workspace_dir)` returning `(service_name, service_url)`; local → unchanged `docker_manager.deploy()`.
- "Health check" step now shows the service URL for cloudrun or port for local.
- "Test chat" step: cloudrun sets `agent.service_url` temporarily and calls `cloudrun_manager.chat()`; local sets `agent.container_port` and calls `docker_manager.chat()`. Empty-reply check unified after both branches.
- "Test endpoints" step: per-endpoint dispatch to `cloudrun_manager.call_endpoint()` or `docker_manager.call_endpoint()` based on DEPLOY_MODE; cleanup on failure uses the correct manager.
- Final DB commit: cloudrun mode writes `cloudrun_service_name` + `service_url`; local mode writes `container_id` + `container_port`.

**frontend/src/types.ts**
- Added `service_url: string | null` and `cloudrun_service_name: string | null` to the `Agent` interface after `container_port`.

**frontend/src/pages/AgentPage.tsx**
- `webpageUrl` now prefers `agent.service_url` (for cloudrun agents), falls back to `http://localhost:{container_port}/` (local), then `null`.

---

#### Design Notes

- `cloudrun_manager` is lazy-imported inside the cloudrun branch (`from app import cloudrun_manager`) so local deployments have zero dependency on it.
- `DEPLOY_MODE` is a module-level constant evaluated once at startup, not per-request — safe for threading.
- All local paths are byte-for-byte identical to the pre-task logic; local mode is the default and cannot be accidentally activated by cloudrun env vars.
