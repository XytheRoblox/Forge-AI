# Task 6 Report: Deployment Scripts and Cleanup

**Status:** COMPLETE  
**Commit:** d604ff8

## What was done

### Files created
- `scripts/push_images.sh` — builds and pushes `agent-runtime` plus 4 MCP pack images (`wolframalpha`, `playwright`, `research_pack`, `dev_pack`) to GCP Artifact Registry. Requires `GCP_PROJECT_ID`; defaults `GCP_REGION=us-central1`, `GCP_ARTIFACT_REPO=forge`. Marked executable.
- `scripts/cloudrun_deploy.sh` — one-time GCP setup: enables Cloud Run + Artifact Registry APIs, creates the registry (idempotent), configures Docker auth, calls `push_images.sh`, then deploys all 4 MCP packs as Cloud Run services with `--allow-unauthenticated --min-instances=1`. Prints env var block and service URLs at the end. Marked executable.

### Files deleted
- `scripts/azure_deploy.sh` — removed via `git rm`
- `backend/app/ollama_manager.py` — removed via `git rm` (Featherless AI replaces local inference)

### Files modified
- `backend/app/build_pipeline.py` line 12: removed `ollama_manager` from top-level import (`from app import docker_manager, mcp_manager, webpage_gen, workspace`). Added lazy `from app import ollama_manager` inside the `if agent.model_provider == "ollama" and DEPLOY_MODE == "local":` branch (line ~169) so local dev still works.
- `backend/.env.example`: appended GCP section (`GCP_PROJECT_ID`, `GCP_REGION`, `GCP_ARTIFACT_REPO`, `DEPLOY_MODE=local`).

### No changes needed
- `backend/app/docker_manager.py` — already had a lazy `from app import ollama_manager` inside `if agent.model_provider == "ollama":` (line ~145). No modification required.

## Backward compatibility
`DEPLOY_MODE=local` (the default) continues to work with Ollama agents — the lazy import ensures `ollama_manager` is only loaded when an Ollama agent deploys locally, so startup doesn't fail in Cloud Run or Featherless-only environments.
