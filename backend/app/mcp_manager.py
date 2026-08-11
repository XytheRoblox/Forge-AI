import os
import socket
import time
from pathlib import Path
from typing import Optional

from app import docker_manager

MCP_SERVERS_DIR = Path(__file__).resolve().parent.parent / "mcp_servers"

# Set only in the split-VM deployment, where capability containers run on a
# separate host from the one running this backend (and creating per-agent
# containers). CAPABILITIES_DOCKER_HOST is an ssh:// URL the `docker` SDK
# connects through (e.g. "ssh://azureuser@10.0.0.5") — SSH rather than the
# raw Docker TCP API, so the only thing that needs to be network-reachable
# is port 22, not an unauthenticated Docker socket. CAPABILITIES_HOST is
# just that host's address (e.g. "10.0.0.5"), used to build the URL agent
# containers actually call at runtime — a real container-name DNS lookup
# only resolves within one Docker daemon's own network, so once capability
# containers live on a different daemon entirely, they have to be addressed
# by host:published-port instead. Neither var being set (plain local dev)
# keeps every bit of this on the exact same single-daemon path as before.
CAPABILITIES_DOCKER_HOST = os.environ.get("CAPABILITIES_DOCKER_HOST")
CAPABILITIES_HOST = os.environ.get("CAPABILITIES_HOST")

_remote_client = None


def _get_client():
    """The Docker client capability containers should be created through —
    the remote one over SSH if this deployment splits capabilities onto
    their own host, otherwise the same local client agent containers use."""
    global _remote_client
    if not CAPABILITIES_DOCKER_HOST:
        return docker_manager._get_client()
    if _remote_client is not None:
        return _remote_client
    try:
        import docker
        from docker.errors import DockerException
    except ImportError as exc:
        raise RuntimeError("The `docker` package is not installed.") from exc
    try:
        client = docker.DockerClient(base_url=CAPABILITIES_DOCKER_HOST)
        client.ping()
    except DockerException as exc:
        raise RuntimeError(
            f"Could not reach the capabilities host at {CAPABILITIES_DOCKER_HOST!r}: {exc}"
        ) from exc
    _remote_client = client
    return _remote_client


def _ensure_network() -> Optional[str]:
    """Only meaningful when capabilities run on the same daemon as agent
    containers (local dev) — that's what lets them resolve each other by
    container name. In split-VM mode there's no shared Docker network to
    join at all (the two daemons don't share one), so this is a no-op and
    ensure_running() addresses capability containers by CAPABILITIES_HOST
    instead."""
    if CAPABILITIES_DOCKER_HOST:
        return None
    return docker_manager.ensure_network()

# Platform-provided key pools, so a keyed capability works out of the box
# without every user having to sign up for and paste in their own key —
# an agent's own capability_api_keys entry always takes priority when
# present (that gives it its own quota instead of sharing the pool). Up to
# 3 app IDs can be configured per capability so usage spreads across them
# instead of every agent hammering a single free-tier key.
CAPABILITY_KEY_POOL_ENV_VARS = {
    "wolfram_alpha": ["WOLFRAM_ALPHA_APP_ID", "WOLFRAM_ALPHA_APP_ID_2", "WOLFRAM_ALPHA_APP_ID_3"],
    "firecrawl": ["FIRECRAWL_API_KEY"],
}


def platform_key_pool(capability_key: str) -> list[str]:
    names = CAPABILITY_KEY_POOL_ENV_VARS.get(capability_key, [])
    return [value for name in names if (value := os.environ.get(name))]


def pick_platform_key(capability_key: str, agent_id: int) -> Optional[str]:
    pool = platform_key_pool(capability_key)
    if not pool:
        return None
    return pool[agent_id % len(pool)]

# One shared container per capability type — built/started on demand the
# first time any agent needs it, then reused across agents and builds
# (unlike per-agent containers, these are never stopped/recreated per build).
MCP_SERVER_SPECS = {
    "wolfram_alpha": {
        "build_dir": MCP_SERVERS_DIR / "wolframalpha",
        "container_name": "forge-mcp-wolfram_alpha",
        "image_tag": "forge-mcp-wolfram-alpha:latest",
        "internal_port": 8000,
        "sse_path": "/sse",
        "env_passthrough": ["WOLFRAM_ALPHA_APP_ID"],
    },
    "firecrawl": {
        "build_dir": MCP_SERVERS_DIR / "firecrawl",
        "container_name": "forge-mcp-firecrawl",
        "image_tag": "forge-mcp-firecrawl:latest",
        "internal_port": 8000,
        "sse_path": "/sse",
        "env_passthrough": ["FIRECRAWL_API_KEY"],
    },
    # Keyless and stateless — the tool's output depends only on its arguments,
    # so there is nothing to keep per-agent and one container serves everyone.
    "desmos": {
        "build_dir": MCP_SERVERS_DIR / "desmos",
        "container_name": "forge-mcp-desmos",
        "image_tag": "forge-mcp-desmos:latest",
        "internal_port": 8000,
        "sse_path": "/sse",
        "env_passthrough": [],
    },
    "playwright": {
        "build_dir": MCP_SERVERS_DIR / "playwright",
        "container_name": "forge-mcp-playwright",
        "image_tag": "forge-mcp-playwright:latest",
        "internal_port": 8931,
        "sse_path": "/sse",
        "env_passthrough": [],
    },
    # --- "Packs": several reference MCP servers bridged from stdio to SSE
    # and bundled into ONE container via mcp-proxy's --named-server mode
    # (each exposed at its own path, e.g. /servers/fetch/sse, on the SAME
    # port) — so a task-themed group of capabilities costs one running
    # container instead of one each. Multiple capability keys below
    # deliberately share the same build_dir/container_name/image_tag; that's
    # not a copy-paste accident, it's the whole point. ensure_running()
    # doesn't need to know or care that they're bundled — "start/reuse this
    # container, return this path" is exactly what it already does.
    #
    # A real limitation carried over from solo wrapped servers: a key is
    # still only read from the container's env at startup (no per-call
    # override), so these remain platform-key-only, not per-agent BYOK.
    # A NEW risk specific to bundling: one named server crashing at startup
    # for want of its API key can take the whole process — and every OTHER
    # capability in that pack — down with it. Each pack's entrypoint.sh
    # guards against this by only including a keyed named server in the
    # command line when its env var is actually present.
    "time": {
        "build_dir": MCP_SERVERS_DIR / "research_pack",
        "container_name": "forge-mcp-research-pack",
        "image_tag": "forge-mcp-research-pack:latest",
        "internal_port": 8000,
        "sse_path": "/servers/time/sse",
        "env_passthrough": [],
    },
    "fetch": {
        "build_dir": MCP_SERVERS_DIR / "research_pack",
        "container_name": "forge-mcp-research-pack",
        "image_tag": "forge-mcp-research-pack:latest",
        "internal_port": 8000,
        "sse_path": "/servers/fetch/sse",
        "env_passthrough": [],
    },
    "sequential_thinking": {
        "build_dir": MCP_SERVERS_DIR / "research_pack",
        "container_name": "forge-mcp-research-pack",
        "image_tag": "forge-mcp-research-pack:latest",
        "internal_port": 8000,
        "sse_path": "/servers/sequential_thinking/sse",
        "env_passthrough": [],
    },
    "filesystem": {
        "build_dir": MCP_SERVERS_DIR / "dev_pack",
        "container_name": "forge-mcp-dev-pack",
        "image_tag": "forge-mcp-dev-pack:latest",
        "internal_port": 8000,
        "sse_path": "/servers/filesystem/sse",
        "env_passthrough": [],
    },
    "github": {
        "build_dir": MCP_SERVERS_DIR / "dev_pack",
        "container_name": "forge-mcp-dev-pack",
        "image_tag": "forge-mcp-dev-pack:latest",
        "internal_port": 8000,
        "sse_path": "/servers/github/sse",
        "env_passthrough": [],
    },
}

# Container creation (env vars, volumes) only ever happens once per shared
# container, triggered by whichever capability in a pack happens to be
# ensure_running() first — which one that is depends on an agent's own
# capability order, so it can't be any single capability's own
# "env_passthrough"/"volume" entry above. Keyed by container_name instead,
# so it applies no matter which pack member triggers creation.
_PACK_ENV_PASSTHROUGH = {
    "forge-mcp-dev-pack": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
}

# Shared scratch space across every agent using the filesystem capability —
# NOT a private per-agent directory (the shared-container model doesn't fit
# that), persisted in a named volume so it survives container restarts.
_PACK_VOLUMES = {
    "forge-mcp-dev-pack": {"name": "forge-mcp-filesystem-scratch", "bind": "/scratch"},
}


def _wait_for_port(host_port: int, timeout: float = 60.0) -> None:
    # In split-VM mode the container we just started is on a different
    # machine, so "is it listening" has to be checked from here, over the
    # network, against CAPABILITIES_HOST — not "localhost".
    probe_host = CAPABILITIES_HOST or "localhost"
    deadline = time.time() + timeout
    last_error: Optional[Exception] = None
    while time.time() < deadline:
        try:
            with socket.create_connection((probe_host, host_port), timeout=2.0):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.5)
    raise RuntimeError(f"MCP server did not start listening in time ({last_error}).")


def _assert_container_healthy(container, mcp_server_key: str, restarts_before: int) -> None:
    """Fail a capability that came up dead, rather than reporting it started.

    _wait_for_port only proves something accepted a TCP connection on the
    PUBLISHED port — and Docker's userland proxy accepts on that port whether
    or not anything inside the container is actually listening. A server that
    exits immediately therefore sails through the port check while its
    container sits in a crash loop, and the agent only finds out later when
    every tool call fails. Comparing the restart count across the startup
    window catches exactly that, without flagging a long-running container
    that happened to restart legitimately at some point in the past."""
    container.reload()
    status = container.status
    restarts_after = container.attrs.get("RestartCount", 0)
    if status == "running" and restarts_after == restarts_before:
        return
    try:
        logs = container.logs(tail=15).decode("utf-8", "replace").strip()
    except Exception:  # noqa: BLE001 - diagnostics only; never mask the real failure
        logs = "(no logs available)"
    reason = (
        f"it is {status}" if status != "running" else f"it restarted {restarts_after - restarts_before}x while starting"
    )
    raise RuntimeError(
        f"the {mcp_server_key!r} container did not stay up — {reason}. Last output:\n{logs}"
    )


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
    restarts_before = container.attrs.get("RestartCount", 0)
    _wait_for_port(host_port)
    _assert_container_healthy(container, mcp_server_key, restarts_before)

    if CAPABILITIES_HOST:
        return f"http://{CAPABILITIES_HOST}:{host_port}{spec['sse_path']}"
    return f"http://{spec['container_name']}:{spec['internal_port']}{spec['sse_path']}"
