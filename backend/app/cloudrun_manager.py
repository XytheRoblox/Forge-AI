import os
import subprocess
import time
from pathlib import Path
from typing import Optional

import httpx

from app import registry

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

    env_vars = [
        f"MODEL_PROVIDER={agent.model_provider}",
        f"MODEL_ID={agent.model_id}",
        f"MODEL_SUPPORTS_VISION={'1' if registry.supports_vision(agent.model_provider, agent.model_id) else '0'}",
    ]
    has_featherless_key = False
    if agent.model_api_key:
        key_name = PROVIDER_ENV_VAR.get(agent.model_provider, "API_KEY")
        env_vars.append(f"{key_name}={agent.model_api_key}")
        has_featherless_key = key_name == "FEATHERLESS_API_KEY"
    elif agent.model_provider == "featherless" and os.environ.get("FEATHERLESS_API_KEY"):
        env_vars.append(f"FEATHERLESS_API_KEY={os.environ['FEATHERLESS_API_KEY']}")
        has_featherless_key = True
    # Mirrors docker_manager: the vision sidecar always runs on Featherless, so
    # even a non-Featherless agent needs a platform key to be able to see images.
    if not has_featherless_key and os.environ.get("FEATHERLESS_API_KEY"):
        env_vars.append(f"FEATHERLESS_API_KEY={os.environ['FEATHERLESS_API_KEY']}")

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
