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
