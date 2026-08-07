import os
import socket
import time
from pathlib import Path
from typing import Optional

from app import docker_manager

MCP_SERVERS_DIR = Path(__file__).resolve().parent.parent / "mcp_servers"

# Platform-provided key pools, so a keyed capability works out of the box
# without every user having to sign up for and paste in their own key —
# an agent's own capability_api_keys entry always takes priority when
# present (that gives it its own quota instead of sharing the pool). Up to
# 3 app IDs can be configured per capability so usage spreads across them
# instead of every agent hammering a single free-tier key.
CAPABILITY_KEY_POOL_ENV_VARS = {
    "wolfram_alpha": ["WOLFRAM_ALPHA_APP_ID", "WOLFRAM_ALPHA_APP_ID_2", "WOLFRAM_ALPHA_APP_ID_3"],
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
    # (e.g. brave_search with no BRAVE_API_KEY) can take the whole process
    # — and every OTHER capability in that pack — down with it. Each pack's
    # own entrypoint.sh guards against this by only including a keyed named
    # server in the command line when its env var is actually present.
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
    "brave_search": {
        "build_dir": MCP_SERVERS_DIR / "research_pack",
        "container_name": "forge-mcp-research-pack",
        "image_tag": "forge-mcp-research-pack:latest",
        "internal_port": 8000,
        "sse_path": "/servers/brave_search/sse",
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
    "forge-mcp-research-pack": ["BRAVE_API_KEY"],
    "forge-mcp-dev-pack": ["GITHUB_PERSONAL_ACCESS_TOKEN"],
}

# Shared scratch space across every agent using the filesystem capability —
# NOT a private per-agent directory (the shared-container model doesn't fit
# that), persisted in a named volume so it survives container restarts.
_PACK_VOLUMES = {
    "forge-mcp-dev-pack": {"name": "forge-mcp-filesystem-scratch", "bind": "/scratch"},
}


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
    raise RuntimeError(f"MCP server did not start listening in time ({last_error}).")


def ensure_running(mcp_server_key: str) -> str:
    """Ensure the shared MCP server container for this key is built and
    running, and return its internal (Docker-network) MCP SSE URL."""
    spec = MCP_SERVER_SPECS.get(mcp_server_key)
    if spec is None:
        raise RuntimeError(f"Unknown MCP server: {mcp_server_key!r}")

    client = docker_manager._get_client()
    network = docker_manager.ensure_network()

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

    return f"http://{spec['container_name']}:{spec['internal_port']}{spec['sse_path']}"
