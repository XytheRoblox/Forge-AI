import json
import shutil
from pathlib import Path

from app.registry import CAPABILITY_OPTIONS

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent / "agent_workspaces"

SYSTEM_PROMPT_FENCE_START = "## System Prompt\n```\n"
SYSTEM_PROMPT_FENCE_END = "\n```\n"

MEMORY_SECTION_HEADER = "## Memory"
TOOL_LOG_SECTION_HEADER = "## Tool Call Log"


def workspace_dir(agent_id: int) -> Path:
    path = WORKSPACE_ROOT / str(agent_id)
    path.mkdir(parents=True, exist_ok=True)
    (path / "web").mkdir(parents=True, exist_ok=True)
    return path


def write_manifesto(agent) -> None:
    capabilities = (
        "\n".join(f"- {key}" for key in agent.capability_keys)
        if agent.capability_keys
        else "(none attached)"
    )
    content = f"""# {agent.name}

## Manifesto
{agent.manifesto or "(none — system prompt was written directly)"}

{SYSTEM_PROMPT_FENCE_START}{agent.system_prompt or ""}{SYSTEM_PROMPT_FENCE_END}
## Model
{agent.model_provider} / {agent.model_id}

## Capabilities
{capabilities}
"""
    (workspace_dir(agent.id) / "MANIFESTO.md").write_text(content)


def write_cache_if_missing(agent) -> None:
    path = workspace_dir(agent.id) / "CACHE.md"
    if path.exists():
        return
    # Memory is long-term and survives everything; the tool call log is
    # working memory for multi-step tasks, written by the runtime after every
    # tool call and trimmed to the most recent handful. (An earlier "## Tool
    # Response Cache" section lived here that nothing ever read or wrote —
    # this replaces it with one the runtime actually uses.)
    content = f"""# Cache

{MEMORY_SECTION_HEADER}
(empty)

{TOOL_LOG_SECTION_HEADER}
(empty)
"""
    path.write_text(content)


def write_cron(agent) -> None:
    if agent.cron_jobs:
        lines = "\n".join(
            f"{job['cron_expression']} :: {job['instruction']}" for job in agent.cron_jobs
        )
    else:
        lines = "(no scheduled jobs)"
    content = f"""# Scheduled Jobs

Each job is one line: `CRON_EXPRESSION :: INSTRUCTION`. Regenerated on every build.

{lines}
"""
    (workspace_dir(agent.id) / "CRON.md").write_text(content)


def write_endpoints(agent) -> None:
    path = workspace_dir(agent.id) / "endpoints.json"
    path.write_text(json.dumps(agent.endpoints, indent=2))


def write_theme(agent) -> None:
    path = workspace_dir(agent.id) / "theme.json"
    path.write_text(json.dumps({"accent": agent.theme_color}, indent=2))


def write_capabilities(agent, capability_urls: dict[str, str], effective_keys: dict[str, str]) -> None:
    """capability_urls: {capability_key: resolved internal MCP SSE url},
    already resolved by the build pipeline (only wired + MCP-backed
    capabilities the agent has attached). effective_keys: {capability_key:
    api key to use}, already resolved by the build pipeline as this agent's
    own key if it provided one, else a rotated platform-provided key — the
    shared MCP server container has no key of its own, so a key must ride
    along with every tool call instead."""
    # The display name and icon ride along so the runtime can label a tool call
    # by its capability's brand ("WolframAlpha 🧮") rather than by the raw MCP
    # tool identifier. registry is the single source of truth for both.
    meta = {c.key: c for c in CAPABILITY_OPTIONS}
    entries = [
        {
            "key": key,
            "mcp_url": url,
            "api_key": effective_keys.get(key),
            "label": meta[key].name if key in meta else key,
            "icon": meta[key].icon if key in meta else "",
        }
        for key, url in capability_urls.items()
    ]
    path = workspace_dir(agent.id) / "capabilities.json"
    path.write_text(json.dumps(entries, indent=2))


def remove_workspace(agent_id: int) -> None:
    path = WORKSPACE_ROOT / str(agent_id)
    if path.exists():
        shutil.rmtree(path)


def ensure_workspace(agent) -> Path:
    write_manifesto(agent)
    write_cron(agent)
    write_endpoints(agent)
    write_theme(agent)
    write_cache_if_missing(agent)
    return workspace_dir(agent.id)
