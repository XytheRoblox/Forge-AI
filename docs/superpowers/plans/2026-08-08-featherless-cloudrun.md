# Featherless AI + Google Cloud Run Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Azure hosting with Google Cloud Run for agent/MCP containers, and add Featherless AI as a new LLM provider with full tool-use support.

**Architecture:** Featherless AI handles LLM inference via an OpenAI-compatible API (same integration pattern as Groq). Google Cloud Run hosts agent containers and MCP pack services as serverless containers that scale to zero. A `DEPLOY_MODE` env var switches between local Docker (dev) and Cloud Run (prod) — no breaking changes to the existing local workflow.

**Tech Stack:** Python FastAPI, Google Cloud Run Admin API (`google-cloud-run`), OpenAI Python SDK (for Featherless), Docker/Artifact Registry, React/TypeScript frontend.

## Global Constraints

- Python 3.11 minimum (matches existing Dockerfile)
- All new backend deps pinned to exact versions in requirements.txt
- `DEPLOY_MODE=local` must remain the default — existing local Docker dev flow unchanged
- No changes to the MCP server container images themselves (only how/where they're deployed)
- Frontend must work with both local Docker agents (localhost:port) and Cloud Run agents (https:// URL)
- Agent runtime Dockerfile stays based on `python:3.11-slim`

---

## File Structure

**New files:**
| File | Responsibility |
|------|----------------|
| `backend/app/featherless_client.py` | Featherless AI client initialization |
| `backend/app/cloudrun_manager.py` | Cloud Run deploy/stop/route/health for agent containers |
| `backend/app/mcp_cloudrun.py` | Cloud Run deploy/management for shared MCP pack services |
| `scripts/cloudrun_deploy.sh` | One-time GCP infra setup (Artifact Registry, MCP services) |
| `scripts/push_images.sh` | Build + push all Docker images to Artifact Registry |
| `backend/tests/test_featherless.py` | Tests for Featherless provider integration |
| `backend/tests/test_cloudrun_manager.py` | Tests for Cloud Run manager |

**Modified files:**
| File | Change |
|------|--------|
| `backend/app/registry.py` | Add Featherless model options |
| `backend/app/docker_manager.py` | Add `featherless` to `PROVIDER_ENV_VAR`; add deploy-mode branching |
| `backend/app/build_pipeline.py` | Branch build steps on `DEPLOY_MODE` |
| `backend/app/models.py` | Add `service_url` field to Agent model |
| `backend/app/schemas.py` | Expose `service_url` in AgentRead |
| `backend/app/mcp_manager.py` | Add Cloud Run fallback in `ensure_running()` |
| `backend/agent_runtime/app.py` | Add Featherless chat handler |
| `backend/agent_runtime/requirements.txt` | Add `openai` package |
| `backend/requirements.txt` | Add `google-cloud-run` package |
| `backend/.env.example` | Add Featherless + GCP env vars |
| `frontend/src/types.ts` | Add `service_url` to Agent interface |
| `frontend/src/pages/AgentPage.tsx` | Use `service_url` for iframe when available |

**Deleted files:**
| File | Reason |
|------|--------|
| `scripts/azure_deploy.sh` | Replaced by `cloudrun_deploy.sh` |
| `backend/app/ollama_manager.py` | Featherless replaces local inference |

---

### Task 1: Add Featherless AI as a Model Provider

**Files:**
- Modify: `backend/app/registry.py:3-256`
- Modify: `backend/app/docker_manager.py:13-15`
- Modify: `backend/.env.example`
- Create: `backend/tests/test_featherless.py`

**Interfaces:**
- Consumes: existing `ModelOption` schema from `backend/app/schemas.py`
- Produces: `featherless` entries in `MODEL_OPTIONS` list; `"featherless": "FEATHERLESS_API_KEY"` in `PROVIDER_ENV_VAR`

- [ ] **Step 1: Add Featherless models to registry.py**

Insert after the Groq models block (line 78) and before the OpenAI block (line 87):

```python
    # --- Featherless AI — OpenAI-compatible serverless inference, needs FEATHERLESS_API_KEY ---
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="meta-llama/Meta-Llama-3.1-70B-Instruct",
        label="Llama 3.1 70B Instruct",
        description="Meta's flagship open model on Featherless — strong reasoning and tool use, serverless GPU inference.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="meta-llama/Meta-Llama-3.1-8B-Instruct",
        label="Llama 3.1 8B Instruct",
        description="Fast and capable smaller Llama model on Featherless. Good for simple agents where speed matters.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="mistralai/Mistral-Nemo-Instruct-2407",
        label="Mistral Nemo 12B",
        description="Mistral's efficient mid-size model on Featherless. Good balance of speed and capability.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="Qwen/Qwen2.5-72B-Instruct",
        label="Qwen 2.5 72B",
        description="Alibaba's large multilingual model on Featherless. Strong at coding and multilingual tasks.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="NousResearch/Meta-Llama-3.1-70B-Instruct",
        label="Nous Llama 3.1 70B",
        description="Nous Research's fine-tune of Llama 3.1 70B on Featherless. Enhanced instruction following.",
        available=True,
    ),
```

- [ ] **Step 2: Add featherless to PROVIDER_ENV_VAR in docker_manager.py**

Change line 13-15 of `backend/app/docker_manager.py` from:

```python
PROVIDER_ENV_VAR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
}
```

To:

```python
PROVIDER_ENV_VAR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "featherless": "FEATHERLESS_API_KEY",
}
```

- [ ] **Step 3: Update .env.example with Featherless key**

Append to `backend/.env.example`:

```bash

# Featherless AI — serverless GPU inference for open-source models.
# Each agent can supply their own key via the wizard; this is the platform fallback.
# Sign up at featherless.ai to get an API key.
FEATHERLESS_API_KEY=
```

- [ ] **Step 4: Write test for registry additions**

Create `backend/tests/test_featherless.py`:

```python
from app.registry import MODEL_OPTIONS
from app.docker_manager import PROVIDER_ENV_VAR


def test_featherless_models_in_registry():
    featherless_models = [m for m in MODEL_OPTIONS if m.provider == "featherless"]
    assert len(featherless_models) >= 5
    for model in featherless_models:
        assert model.available is True
        assert model.provider_label == "Featherless AI"
        assert "/" in model.model_id  # HuggingFace-style org/model format


def test_featherless_in_provider_env_var():
    assert "featherless" in PROVIDER_ENV_VAR
    assert PROVIDER_ENV_VAR["featherless"] == "FEATHERLESS_API_KEY"
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/arvindsr/Forge/backend && python -m pytest tests/test_featherless.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/registry.py backend/app/docker_manager.py backend/.env.example backend/tests/test_featherless.py
git commit -m "feat: add Featherless AI as a model provider in registry"
```

---

### Task 2: Add Featherless Chat Handler to Agent Runtime

**Files:**
- Modify: `backend/agent_runtime/app.py:329-401`
- Modify: `backend/agent_runtime/requirements.txt`

**Interfaces:**
- Consumes: `MODEL_PROVIDER="featherless"`, `MODEL_ID`, `FEATHERLESS_API_KEY` env vars; `_TOOL_INDEX` dict from MCP discovery; `_set_status()`, `_strip_thinking()`, `_execute_tool()` helpers
- Produces: Featherless branch in `_generate_reply()` that returns a string reply after multi-round tool-use loops

- [ ] **Step 1: Add openai to agent runtime requirements**

Change `backend/agent_runtime/requirements.txt` to:

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
anthropic==0.68.0
groq==1.0.0
openai==1.82.0
httpx==0.28.1
jsonschema==4.23.0
croniter==3.0.4
mcp==1.29.0
```

- [ ] **Step 2: Add Featherless client initializer in app.py**

Insert after the `_get_groq()` function (after line 77) in `backend/agent_runtime/app.py`:

```python
_featherless_client = None


def _get_featherless():
    global _featherless_client
    if _featherless_client is None:
        from openai import OpenAI

        api_key = os.environ.get("FEATHERLESS_API_KEY")
        if not api_key:
            raise RuntimeError("FEATHERLESS_API_KEY is not set in this container.")
        _featherless_client = OpenAI(
            base_url="https://api.featherless.ai/v1",
            api_key=api_key,
        )
    return _featherless_client
```

- [ ] **Step 3: Add Featherless branch in _generate_reply()**

Insert after the `elif MODEL_PROVIDER == "groq":` block (after line 401) and before the `elif MODEL_PROVIDER == "ollama":` block in `backend/agent_runtime/app.py`:

```python
    elif MODEL_PROVIDER == "featherless":
        from openai import NOT_GIVEN

        client = _get_featherless()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": info["description"],
                    "parameters": info["input_schema"],
                },
            }
            for name, info in _TOOL_INDEX.items()
        ]
        messages = [{"role": "system", "content": system_prompt}, *history]

        for _ in range(MAX_TOOL_ITERATIONS):
            _set_status(f"Asking {MODEL_ID}…")
            kwargs = {"model": MODEL_ID, "max_tokens": 2048, "messages": messages}
            if tools:
                kwargs["tools"] = tools
            response = client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            if not message.tool_calls:
                _set_status("Writing a reply…")
                return _strip_thinking(message.content or "")

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in message.tool_calls
                    ],
                }
            )
            for tool_call in message.tool_calls:
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}
                _set_status(f"Using {tool_call.function.name}…")
                result_text = _execute_tool(tool_call.function.name, arguments)
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result_text})

        _set_status("Writing a final answer…")
        response = client.chat.completions.create(
            model=MODEL_ID, max_tokens=2048, messages=messages
        )
        return _strip_thinking(response.choices[0].message.content or "")
```

- [ ] **Step 4: Verify the Dockerfile doesn't need changes**

Read `backend/agent_runtime/Dockerfile` — it already does `pip install -r requirements.txt` which will pull in `openai`. No change needed.

- [ ] **Step 5: Commit**

```bash
git add backend/agent_runtime/app.py backend/agent_runtime/requirements.txt
git commit -m "feat: add Featherless AI chat handler with tool-use loop in agent runtime"
```

---

### Task 3: Add Cloud Run Manager for Agent Deployment

**Files:**
- Create: `backend/app/cloudrun_manager.py`
- Modify: `backend/requirements.txt`
- Create: `backend/tests/test_cloudrun_manager.py`

**Interfaces:**
- Consumes: `Agent` model from `backend/app/models.py`; `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_ARTIFACT_REPO` env vars
- Produces: `deploy_agent(agent, workspace_dir) -> tuple[str, str]` (service_name, service_url), `stop_agent(agent) -> None`, `chat(agent, history) -> str`, `call_endpoint(agent, method, path, payload) -> dict`, `is_available() -> bool`

- [ ] **Step 1: Add google-cloud-run to backend requirements**

Change `backend/requirements.txt` to:

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlmodel==0.0.22
anthropic==0.68.0
groq==1.0.0
python-dotenv==1.0.1
docker==7.2.0
paramiko==3.5.0
httpx==0.28.1
jsonschema==4.23.0
croniter==3.0.4
google-cloud-run==0.10.12
```

- [ ] **Step 2: Create cloudrun_manager.py**

Create `backend/app/cloudrun_manager.py`:

```python
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

import httpx

RUNTIME_DIR = Path(__file__).resolve().parent.parent / "agent_runtime"
CONTAINER_PORT = 8080

GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")
GCP_ARTIFACT_REPO = os.environ.get("GCP_ARTIFACT_REPO", "forge")

PROVIDER_ENV_VAR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "featherless": "FEATHERLESS_API_KEY",
}


def _image_uri(agent_id: int) -> str:
    return f"{GCP_REGION}-docker.pkg.dev/{GCP_PROJECT_ID}/{GCP_ARTIFACT_REPO}/agent-{agent_id}:latest"


def _service_name(agent_id: int) -> str:
    return f"forge-agent-{agent_id}"


def is_available() -> bool:
    if not GCP_PROJECT_ID:
        return False
    try:
        result = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _build_and_push(agent_id: int, workspace_dir: Path) -> str:
    image_uri = _image_uri(agent_id)
    dockerfile_content = f"""FROM {GCP_REGION}-docker.pkg.dev/{GCP_PROJECT_ID}/{GCP_ARTIFACT_REPO}/agent-runtime:latest
COPY workspace/ /workspace/
"""
    build_dir = workspace_dir.parent / f".cloudrun-build-{agent_id}"
    build_dir.mkdir(exist_ok=True)
    (build_dir / "Dockerfile").write_text(dockerfile_content)

    workspace_dest = build_dir / "workspace"
    if workspace_dest.exists():
        import shutil
        shutil.rmtree(workspace_dest)
    import shutil
    shutil.copytree(workspace_dir, workspace_dest)

    subprocess.run(
        ["docker", "build", "-t", image_uri, "."],
        cwd=build_dir, check=True, capture_output=True, text=True,
    )
    subprocess.run(
        ["docker", "push", image_uri],
        check=True, capture_output=True, text=True,
    )

    import shutil
    shutil.rmtree(build_dir)
    return image_uri


def deploy_agent(agent, workspace_dir: Path) -> tuple[str, str]:
    image_uri = _build_and_push(agent.id, workspace_dir)
    service_name = _service_name(agent.id)

    env_vars = [f"MODEL_PROVIDER={agent.model_provider}", f"MODEL_ID={agent.model_id}"]
    if agent.model_api_key:
        key_name = PROVIDER_ENV_VAR.get(agent.model_provider, "API_KEY")
        env_vars.append(f"{key_name}={agent.model_api_key}")

    cmd = [
        "gcloud", "run", "deploy", service_name,
        f"--image={image_uri}",
        f"--region={GCP_REGION}",
        f"--project={GCP_PROJECT_ID}",
        f"--port={CONTAINER_PORT}",
        "--min-instances=0",
        "--max-instances=3",
        "--timeout=300",
        "--allow-unauthenticated",
        "--cpu=1",
        "--memory=512Mi",
        f"--set-env-vars={','.join(env_vars)}",
        "--format=value(status.url)",
        "--quiet",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"Cloud Run deploy failed: {result.stderr}")

    service_url = result.stdout.strip()
    if not service_url:
        service_url = _get_service_url(service_name)

    _wait_for_health(service_url)
    return service_name, service_url


def _get_service_url(service_name: str) -> str:
    result = subprocess.run(
        [
            "gcloud", "run", "services", "describe", service_name,
            f"--region={GCP_REGION}",
            f"--project={GCP_PROJECT_ID}",
            "--format=value(status.url)",
        ],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Could not get service URL: {result.stderr}")
    return result.stdout.strip()


def _wait_for_health(service_url: str, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    last_error: Optional[Exception] = None
    while time.time() < deadline:
        try:
            response = httpx.get(f"{service_url}/health", timeout=10.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(2.0)
    raise RuntimeError(f"Cloud Run service did not become healthy: {last_error}")


def stop_agent(agent) -> None:
    service_name = agent.cloudrun_service_name or _service_name(agent.id)
    subprocess.run(
        [
            "gcloud", "run", "services", "delete", service_name,
            f"--region={GCP_REGION}",
            f"--project={GCP_PROJECT_ID}",
            "--quiet",
        ],
        capture_output=True, text=True, timeout=60,
    )


def chat(agent, history: list[dict]) -> str:
    service_url = agent.service_url
    if not service_url:
        raise RuntimeError("Agent has no Cloud Run service URL. Deploy it again.")
    try:
        response = httpx.post(
            f"{service_url}/chat",
            json={"history": history},
            timeout=180.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except ValueError:
            detail = exc.response.text or f"HTTP {exc.response.status_code}"
        raise RuntimeError(f"Agent service error: {detail}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(
            "Could not reach the agent's Cloud Run service. It may be scaling up — try again in a moment."
        ) from exc
    try:
        return response.json()["reply"]
    except ValueError as exc:
        raise RuntimeError(f"Agent returned non-JSON: {response.text[:200]}") from exc


def call_endpoint(agent, method: str, path: str, payload: dict) -> dict:
    service_url = agent.service_url
    if not service_url:
        raise RuntimeError("Agent has no Cloud Run service URL.")
    try:
        response = httpx.request(
            method, f"{service_url}{path}", json=payload, timeout=60.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except ValueError:
            detail = exc.response.text or f"HTTP {exc.response.status_code}"
        raise RuntimeError(f"Endpoint {path} error: {detail}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not reach endpoint {path}: {exc}") from exc
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"Endpoint {path} non-JSON response: {response.text[:200]}") from exc
```

- [ ] **Step 3: Write tests for cloudrun_manager**

Create `backend/tests/test_cloudrun_manager.py`:

```python
import os
from unittest.mock import patch

from app.cloudrun_manager import _service_name, _image_uri, is_available


def test_service_name_format():
    assert _service_name(1) == "forge-agent-1"
    assert _service_name(42) == "forge-agent-42"


def test_image_uri_format():
    with patch.dict(os.environ, {"GCP_PROJECT_ID": "my-project", "GCP_REGION": "us-central1", "GCP_ARTIFACT_REPO": "forge"}):
        from importlib import reload
        import app.cloudrun_manager as mod
        reload(mod)
        assert "my-project" in mod._image_uri(1)
        assert "agent-1:latest" in mod._image_uri(1)


def test_is_available_without_project_id():
    with patch.dict(os.environ, {"GCP_PROJECT_ID": ""}, clear=False):
        from importlib import reload
        import app.cloudrun_manager as mod
        reload(mod)
        assert mod.is_available() is False
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/arvindsr/Forge/backend && pip install google-cloud-run==0.10.12 && python -m pytest tests/test_cloudrun_manager.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/cloudrun_manager.py backend/requirements.txt backend/tests/test_cloudrun_manager.py
git commit -m "feat: add Cloud Run manager for deploying agent containers"
```

---

### Task 4: Add Cloud Run Support for MCP Packs

**Files:**
- Create: `backend/app/mcp_cloudrun.py`
- Modify: `backend/app/mcp_manager.py:211-262`

**Interfaces:**
- Consumes: `MCP_SERVER_SPECS` from `mcp_manager.py`; `GCP_PROJECT_ID`, `GCP_REGION` env vars
- Produces: `ensure_running(mcp_server_key: str) -> str` that returns a Cloud Run service URL + SSE path

- [ ] **Step 1: Create mcp_cloudrun.py**

Create `backend/app/mcp_cloudrun.py`:

```python
import os
import subprocess
import time
from typing import Optional

import httpx

from app.mcp_manager import MCP_SERVER_SPECS, _PACK_ENV_PASSTHROUGH

GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")
GCP_REGION = os.environ.get("GCP_REGION", "us-central1")
GCP_ARTIFACT_REPO = os.environ.get("GCP_ARTIFACT_REPO", "forge")

_service_urls: dict[str, str] = {}


def _image_tag_to_service_name(image_tag: str) -> str:
    name = image_tag.replace(":latest", "").replace(":", "-")
    return name


def _get_or_deploy_service(container_name: str, image_tag: str) -> str:
    if container_name in _service_urls:
        return _service_urls[container_name]

    service_name = _image_tag_to_service_name(image_tag)
    image_uri = f"{GCP_REGION}-docker.pkg.dev/{GCP_PROJECT_ID}/{GCP_ARTIFACT_REPO}/{service_name}:latest"

    result = subprocess.run(
        [
            "gcloud", "run", "services", "describe", service_name,
            f"--region={GCP_REGION}",
            f"--project={GCP_PROJECT_ID}",
            "--format=value(status.url)",
        ],
        capture_output=True, text=True, timeout=30,
    )

    if result.returncode == 0 and result.stdout.strip():
        url = result.stdout.strip()
        _service_urls[container_name] = url
        return url

    env_vars = []
    pack_env_keys = _PACK_ENV_PASSTHROUGH.get(container_name, [])
    for key in pack_env_keys:
        value = os.environ.get(key)
        if value:
            env_vars.append(f"{key}={value}")

    cmd = [
        "gcloud", "run", "deploy", service_name,
        f"--image={image_uri}",
        f"--region={GCP_REGION}",
        f"--project={GCP_PROJECT_ID}",
        "--port=8000",
        "--min-instances=1",
        "--max-instances=2",
        "--timeout=60",
        "--allow-unauthenticated",
        "--cpu=1",
        "--memory=512Mi",
        "--quiet",
    ]
    if env_vars:
        cmd.append(f"--set-env-vars={','.join(env_vars)}")

    deploy_result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if deploy_result.returncode != 0:
        raise RuntimeError(f"MCP service deploy failed: {deploy_result.stderr}")

    describe_result = subprocess.run(
        [
            "gcloud", "run", "services", "describe", service_name,
            f"--region={GCP_REGION}",
            f"--project={GCP_PROJECT_ID}",
            "--format=value(status.url)",
        ],
        capture_output=True, text=True, timeout=30,
    )
    url = describe_result.stdout.strip()
    if not url:
        raise RuntimeError(f"Could not get URL for MCP service {service_name}")

    _service_urls[container_name] = url
    return url


def ensure_running(mcp_server_key: str) -> str:
    spec = MCP_SERVER_SPECS.get(mcp_server_key)
    if spec is None:
        raise RuntimeError(f"Unknown MCP server: {mcp_server_key!r}")

    service_url = _get_or_deploy_service(spec["container_name"], spec["image_tag"])
    return f"{service_url}{spec['sse_path']}"
```

- [ ] **Step 2: Add deploy-mode branching to mcp_manager.ensure_running()**

Modify the `ensure_running` function in `backend/app/mcp_manager.py`. Replace lines 211-262 with:

```python
def ensure_running(mcp_server_key: str) -> str:
    """Ensure the shared MCP server for this key is running and return its SSE URL.
    In cloudrun mode, delegates to mcp_cloudrun; otherwise uses local Docker."""
    deploy_mode = os.environ.get("DEPLOY_MODE", "local")
    if deploy_mode == "cloudrun":
        from app import mcp_cloudrun
        return mcp_cloudrun.ensure_running(mcp_server_key)

    spec = MCP_SERVER_SPECS.get(mcp_server_key)
    if spec is None:
        raise RuntimeError(f"Unknown MCP server: {mcp_server_key!r}")

    client = _get_client()
    network = _ensure_network()

    from docker.errors import NotFound

    client.images.build(path=str(spec["build_dir"]), tag=spec["image_tag"], rm=True)

    try:
        container = client.containers.get(spec["container_name"])
        if container.status != "running":
            container.start()
    except NotFound:
        env_vars = set(spec["env_passthrough"]) | set(
            _PACK_ENV_PASSTHROUGH.get(spec["container_name"], [])
        )
        env = {key: os.environ[key] for key in env_vars if os.environ.get(key)}
        volume_spec = spec.get("volume") or _PACK_VOLUMES.get(spec["container_name"])
        volumes = None
        if volume_spec:
            volumes = {volume_spec["name"]: {"bind": volume_spec["bind"], "mode": "rw"}}
        container = client.containers.run(
            spec["image_tag"],
            name=spec["container_name"],
            environment=env,
            ports={f"{spec['internal_port']}/tcp": None},
            volumes=volumes,
            network=network,
            detach=True,
            restart_policy={"Name": "unless-stopped"},
        )

    container.reload()
    ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
    bindings = ports.get(f"{spec['internal_port']}/tcp")
    if not bindings:
        raise RuntimeError(f"MCP server {mcp_server_key!r} did not publish its port.")
    host_port = int(bindings[0]["HostPort"])
    _wait_for_port(host_port)

    if CAPABILITIES_HOST:
        return f"http://{CAPABILITIES_HOST}:{host_port}{spec['sse_path']}"
    return f"http://{spec['container_name']}:{spec['internal_port']}{spec['sse_path']}"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/mcp_cloudrun.py backend/app/mcp_manager.py
git commit -m "feat: add Cloud Run deployment path for MCP pack services"
```

---

### Task 5: Update Data Model and Build Pipeline for Deploy Mode Branching

**Files:**
- Modify: `backend/app/models.py:8-26`
- Modify: `backend/app/schemas.py:52-70`
- Modify: `backend/app/build_pipeline.py:139-272`
- Modify: `frontend/src/types.ts:37-56`
- Modify: `frontend/src/pages/AgentPage.tsx:21`

**Interfaces:**
- Consumes: `cloudrun_manager.deploy_agent()`, `cloudrun_manager.chat()`, `cloudrun_manager.stop_agent()`, `cloudrun_manager.call_endpoint()`
- Produces: `Agent.service_url` field; build pipeline that branches on `DEPLOY_MODE`

- [ ] **Step 1: Add service_url to Agent model**

In `backend/app/models.py`, add after line 26 (`container_port`):

```python
    service_url: Optional[str] = None
    cloudrun_service_name: Optional[str] = None
```

- [ ] **Step 2: Add service_url to AgentRead schema**

In `backend/app/schemas.py`, add after `container_port` (line 70):

```python
    service_url: Optional[str] = None
    cloudrun_service_name: Optional[str] = None
```

- [ ] **Step 3: Update build pipeline to branch on DEPLOY_MODE**

In `backend/app/build_pipeline.py`, replace the `_run` function body (lines 139-272). The key changes are:

Add at the top of the file (after the imports):

```python
DEPLOY_MODE = os.environ.get("DEPLOY_MODE", "local")
```

Add `import os` to the imports at the top.

In the `_run` function, replace the "Prepare local model" step (lines 165-177) with:

```python
        step = job.steps[2]
        step.status = "running"
        if agent.model_provider == "ollama" and DEPLOY_MODE == "local":
            step.detail = f"Pulling {agent.model_id!r} (first time can take a few minutes)…"
            try:
                ollama_manager.ensure_model_pulled(agent.model_id)
            except RuntimeError as exc:
                _fail(job, step, str(exc))
                return
            step.status = "success"
            step.detail = f"Model {agent.model_id!r} ready."
        else:
            step.status = "success"
            step.detail = "Not needed (using API-based inference)."
```

Replace the "Start container" step (lines 209-219) with:

```python
        step = job.steps[5]
        step.status = "running"
        if DEPLOY_MODE == "cloudrun":
            step.detail = "Deploying to Cloud Run…"
            try:
                from app import cloudrun_manager
                service_name, service_url = cloudrun_manager.deploy_agent(agent, workspace_dir)
            except RuntimeError as exc:
                _fail(job, step, str(exc))
                return
            step.status = "success"
            step.detail = f"Deployed: {service_url}"
        else:
            step.detail = "Building container image and starting it…"
            try:
                container_id, container_port = docker_manager.deploy(agent, workspace_dir)
            except RuntimeError as exc:
                _fail(job, step, str(exc))
                return
            step.status = "success"
            step.detail = None
```

Replace the "Health check" step (lines 222-226) with:

```python
        step = job.steps[6]
        step.status = "running"
        if DEPLOY_MODE == "cloudrun":
            step.status = "success"
            step.detail = f"Service healthy at {service_url}"
        else:
            step.status = "success"
            step.detail = f"Container healthy on port {container_port}"
```

Replace the "Test chat" step (lines 228-241) with:

```python
        step = job.steps[7]
        step.status = "running"
        step.detail = "Sending a test message…"
        if DEPLOY_MODE == "cloudrun":
            agent.service_url = service_url
            try:
                reply = cloudrun_manager.chat(
                    agent, [{"role": "user", "content": "Say hello in one short sentence."}]
                )
            except RuntimeError as exc:
                _fail(job, step, str(exc))
                cloudrun_manager.stop_agent(agent)
                return
        else:
            agent.container_port = container_port
            try:
                reply = docker_manager.chat(
                    agent, [{"role": "user", "content": "Say hello in one short sentence."}]
                )
            except RuntimeError as exc:
                _fail(job, step, str(exc))
                docker_manager.stop_and_remove(agent)
                return
        if not reply.strip():
            _fail(job, step, "Agent replied with empty text.")
            return
        step.status = "success"
        step.detail = f"Reply: {reply[:80]}"
```

Replace the "Test endpoints" step (lines 243-262) with:

```python
        step = job.steps[8]
        step.status = "running"
        if not agent.endpoints:
            step.status = "success"
            step.detail = "No custom endpoints configured."
        else:
            tested = []
            try:
                for ep in agent.endpoints:
                    payload = _sample_payload(ep["input_schema"])
                    if DEPLOY_MODE == "cloudrun":
                        cloudrun_manager.call_endpoint(agent, ep["method"], ep["path"], payload)
                    else:
                        docker_manager.call_endpoint(agent, ep["method"], ep["path"], payload)
                    tested.append(ep["path"])
            except RuntimeError as exc:
                _fail(job, step, str(exc))
                if DEPLOY_MODE == "cloudrun":
                    cloudrun_manager.stop_agent(agent)
                else:
                    docker_manager.stop_and_remove(agent)
                return
            step.status = "success"
            step.detail = f"Tested: {', '.join(tested)}"
```

Replace the final DB update block (lines 264-272) with:

```python
        for message in session.exec(select(Message).where(Message.agent_id == agent_id)).all():
            session.delete(message)
        agent.status = "deployed"
        agent.deployed_at = datetime.utcnow()
        if DEPLOY_MODE == "cloudrun":
            agent.cloudrun_service_name = service_name
            agent.service_url = service_url
        else:
            agent.container_id = container_id
            agent.container_port = container_port
        session.add(agent)
        session.commit()
        job.status = "success"
```

- [ ] **Step 4: Update frontend Agent type**

In `frontend/src/types.ts`, add after `container_port` (line 55):

```typescript
  service_url: string | null;
  cloudrun_service_name: string | null;
```

- [ ] **Step 5: Update AgentPage to use service_url for iframe**

In `frontend/src/pages/AgentPage.tsx`, replace line 21:

```typescript
  const webpageUrl = agent.container_port ? `http://localhost:${agent.container_port}/` : null;
```

With:

```typescript
  const webpageUrl = agent.service_url
    ? `${agent.service_url}/`
    : agent.container_port
      ? `http://localhost:${agent.container_port}/`
      : null;
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/app/schemas.py backend/app/build_pipeline.py frontend/src/types.ts frontend/src/pages/AgentPage.tsx
git commit -m "feat: branch build pipeline on DEPLOY_MODE, add service_url to Agent model"
```

---

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

---

### Task 7: Integration Test — Full Local Flow with Featherless

**Files:**
- No new files — manual verification

**Interfaces:**
- Consumes: All previous tasks
- Produces: Verified working local flow end-to-end

- [ ] **Step 1: Install updated backend dependencies**

```bash
cd /Users/arvindsr/Forge/backend
pip install -r requirements.txt
```

- [ ] **Step 2: Verify the backend starts without errors**

```bash
cd /Users/arvindsr/Forge/backend
DEPLOY_MODE=local uvicorn app.main:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -s http://localhost:8000/api/health | python3 -m json.tool
curl -s http://localhost:8000/api/models | python3 -c "import sys,json; models=json.load(sys.stdin); featherless=[m for m in models if m['provider']=='featherless']; print(f'{len(featherless)} Featherless models found'); assert len(featherless)>=5"
kill %1
```

Expected: Health check returns `{"status": "ok"}`, 5+ Featherless models listed.

- [ ] **Step 3: Verify frontend shows Featherless models**

```bash
cd /Users/arvindsr/Forge/frontend
npm run dev &
```

Open browser, navigate to wizard step 1 — verify "Featherless AI" appears as a provider group with available models.

- [ ] **Step 4: Run all tests**

```bash
cd /Users/arvindsr/Forge/backend
python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit any test fixes**

```bash
git add -A
git commit -m "fix: test corrections from integration verification"
```

---
