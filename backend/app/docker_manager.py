import time
from pathlib import Path
from typing import Optional

import httpx

IMAGE_TAG = "zovo-agent-runtime:latest"
RUNTIME_DIR = Path(__file__).resolve().parent.parent / "agent_runtime"
CONTAINER_PORT = 8080

NETWORK_NAME = "forge-net"

PROVIDER_ENV_VAR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
}

_client = None


def _get_client():
    global _client
    if _client is not None:
        return _client
    try:
        import docker
        from docker.errors import DockerException
    except ImportError as exc:
        raise RuntimeError("The `docker` package is not installed.") from exc

    try:
        client = docker.from_env()
        client.ping()
    except DockerException as exc:
        raise RuntimeError(
            "Docker is not available. Install Docker Desktop, make sure it's running, "
            "and try again."
        ) from exc
    _client = client
    return _client


def ensure_network() -> str:
    """Idempotently ensure the shared user-defined network exists, so
    containers can reach each other by container name (the default bridge
    network has no inter-container DNS). Returns the network name."""
    from docker.errors import NotFound

    client = _get_client()
    try:
        client.networks.get(NETWORK_NAME)
    except NotFound:
        client.networks.create(NETWORK_NAME, driver="bridge")
    return NETWORK_NAME


def is_available() -> bool:
    try:
        _get_client()
        return True
    except RuntimeError:
        return False


def _ensure_image():
    # Always (re)build rather than skipping when a same-tagged image already
    # exists — Docker's layer cache makes a no-op rebuild cheap (~1s), and
    # this guarantees agent_runtime/ source changes actually take effect on
    # the next deploy instead of silently running a stale image.
    client = _get_client()
    client.images.build(path=str(RUNTIME_DIR), tag=IMAGE_TAG, rm=True)


def _container_name(agent_id: int) -> str:
    return f"zovo-agent-{agent_id}"


def stop_and_remove(agent) -> None:
    """Best-effort stop+remove of an agent's container. Safe to call even if none exists."""
    if not is_available():
        return
    client = _get_client()
    from docker.errors import NotFound

    candidates = [agent.container_id, _container_name(agent.id)]
    for ref in candidates:
        if not ref:
            continue
        try:
            container = client.containers.get(ref)
            container.stop(timeout=5)
            container.remove()
        except NotFound:
            continue


def _wait_for_host_port(container, timeout: float = 10.0) -> int:
    client = _get_client()
    deadline = time.time() + timeout
    while time.time() < deadline:
        container.reload()
        ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
        bindings = ports.get(f"{CONTAINER_PORT}/tcp")
        if bindings:
            return int(bindings[0]["HostPort"])
        time.sleep(0.2)
    raise RuntimeError("Container did not publish its port in time.")


def _wait_for_health(host_port: int, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    last_error = None
    while time.time() < deadline:
        try:
            response = httpx.get(f"http://localhost:{host_port}/health", timeout=2.0)
            if response.status_code == 200:
                return
        except httpx.HTTPError as exc:
            last_error = exc
        time.sleep(0.3)
    raise RuntimeError(f"Agent container did not become healthy in time ({last_error}).")


def deploy(agent, workspace_dir) -> tuple[str, int]:
    """Stop any existing container for this agent and start a fresh one, with
    its workspace directory (MANIFESTO.md, CACHE.md, CRON.md, endpoints.json,
    theme.json, web/) bind-mounted at /workspace.

    Returns (container_id, host_port).
    """
    _get_client()
    _ensure_image()
    network = ensure_network()
    stop_and_remove(agent)

    env = {
        "MODEL_PROVIDER": agent.model_provider,
        "MODEL_ID": agent.model_id,
    }
    if agent.model_provider == "ollama":
        # No API key needed — instead, point at the shared Ollama container
        # (already running by the time this runs; the build pipeline's
        # "Prepare local model" step started it and pulled the model).
        from app import ollama_manager

        internal_url, _ = ollama_manager.ensure_running()
        env["OLLAMA_URL"] = internal_url
    elif agent.model_api_key:
        # Each agent uses its own owner-supplied API key, not a key shared
        # across every agent on this host — build validation already
        # guarantees model_api_key is set before a hosted-API agent deploys.
        env[PROVIDER_ENV_VAR.get(agent.model_provider, "API_KEY")] = agent.model_api_key

    client = _get_client()
    container = client.containers.run(
        IMAGE_TAG,
        name=_container_name(agent.id),
        environment=env,
        ports={f"{CONTAINER_PORT}/tcp": None},
        volumes={str(workspace_dir): {"bind": "/workspace", "mode": "rw"}},
        network=network,
        detach=True,
    )

    try:
        host_port = _wait_for_host_port(container)
        _wait_for_health(host_port)
    except RuntimeError:
        container.stop(timeout=5)
        container.remove()
        raise

    return container.id, host_port


def chat(agent, history: list[dict]) -> str:
    if not agent.container_port:
        raise RuntimeError("Agent has no running container. Deploy it again.")
    try:
        response = httpx.post(
            f"http://localhost:{agent.container_port}/chat",
            json={"history": history},
            # Local Ollama models can take well over a minute to load into RAM
            # on the first request after a deploy (cold-start on CPU-only
            # hardware) — generous enough to cover that without penalizing
            # hosted-API agents, which typically reply in a few seconds anyway.
            timeout=180.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except ValueError:  # response body wasn't JSON at all
            detail = exc.response.text or f"HTTP {exc.response.status_code}"
        raise RuntimeError(f"Agent container error: {detail}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(
            "Could not reach the agent's container. It may have stopped — try redeploying."
        ) from exc
    try:
        return response.json()["reply"]
    except ValueError as exc:
        raise RuntimeError(f"Agent container returned a non-JSON response: {response.text[:200]}") from exc


def call_endpoint(agent, method: str, path: str, payload: dict) -> dict:
    if not agent.container_port:
        raise RuntimeError("Agent has no running container.")
    try:
        response = httpx.request(
            method,
            f"http://localhost:{agent.container_port}{path}",
            json=payload,
            timeout=60.0,
        )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except ValueError:  # response body wasn't JSON at all
            detail = exc.response.text or f"HTTP {exc.response.status_code}"
        raise RuntimeError(f"Endpoint {path} error: {detail}") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not reach endpoint {path}: {exc}") from exc
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError(f"Endpoint {path} returned a non-JSON response: {response.text[:200]}") from exc
