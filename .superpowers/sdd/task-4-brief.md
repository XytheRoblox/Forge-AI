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

