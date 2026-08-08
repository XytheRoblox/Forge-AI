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

