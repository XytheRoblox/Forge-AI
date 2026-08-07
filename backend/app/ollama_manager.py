import json
import socket
import time
from typing import Optional

import httpx

from app import docker_manager

# A single shared container, like the MCP servers — reused across every
# agent that picks an Ollama model, not recreated per build. Models are
# pulled into a named volume so they survive container restarts.
CONTAINER_NAME = "forge-ollama"
IMAGE = "ollama/ollama:latest"
INTERNAL_PORT = 11434
VOLUME_NAME = "forge-ollama-models"


def _wait_for_port(host_port: int, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    last_error: Optional[Exception] = None
    while time.time() < deadline:
        try:
            with socket.create_connection(("localhost", host_port), timeout=2.0):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"Ollama did not start listening in time ({last_error}).")


def ensure_running() -> tuple[str, int]:
    """Ensure the shared Ollama container is built and running on forge-net.
    Returns (internal_url, host_port) — internal_url is what agent
    containers use to reach it, host_port is what this backend process
    itself uses to trigger model pulls."""
    client = docker_manager._get_client()
    network = docker_manager.ensure_network()

    from docker.errors import NotFound

    try:
        container = client.containers.get(CONTAINER_NAME)
        if container.status != "running":
            container.start()
    except NotFound:
        client.images.pull(IMAGE)
        container = client.containers.run(
            IMAGE,
            name=CONTAINER_NAME,
            detach=True,
            network=network,
            volumes={VOLUME_NAME: {"bind": "/root/.ollama", "mode": "rw"}},
            ports={f"{INTERNAL_PORT}/tcp": None},
            restart_policy={"Name": "unless-stopped"},
        )

    container.reload()
    ports = container.attrs.get("NetworkSettings", {}).get("Ports", {})
    bindings = ports.get(f"{INTERNAL_PORT}/tcp")
    if not bindings:
        raise RuntimeError("Ollama did not publish its port.")
    host_port = int(bindings[0]["HostPort"])
    _wait_for_port(host_port)

    return f"http://{CONTAINER_NAME}:{INTERNAL_PORT}", host_port


def ensure_model_pulled(model_id: str, idle_timeout: float = 120.0) -> None:
    """Blocking pull of a model into the shared Ollama container — a no-op
    if it's already present locally. Can take several minutes on first pull
    since models are multi-gigabyte downloads.

    Consumed as a stream of NDJSON progress events (the same way `ollama
    pull`'s own progress bar works), rather than requesting a single
    buffered response with stream=False — over a long multi-minute
    download, a single non-streaming request sits with no bytes moving
    until the very end, and something in the local Docker networking path
    resets it well before it completes. Streaming keeps bytes actively
    flowing the whole time, and idle_timeout only needs to cover the gap
    between progress events, not the whole download."""
    _, host_port = ensure_running()
    try:
        with httpx.stream(
            "POST",
            f"http://localhost:{host_port}/api/pull",
            json={"model": model_id},
            timeout=httpx.Timeout(30.0, read=idle_timeout),
        ) as response:
            response.raise_for_status()
            final_status = ""
            for line in response.iter_lines():
                if not line:
                    continue
                event = json.loads(line)
                if event.get("error"):
                    raise RuntimeError(event["error"])
                final_status = event.get("status", final_status)
            if final_status != "success":
                raise RuntimeError(f"Pull ended with unexpected status: {final_status!r}")
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Could not pull Ollama model {model_id!r}: {exc}") from exc
