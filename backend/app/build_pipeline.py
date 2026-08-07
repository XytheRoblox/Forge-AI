import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import croniter
import jsonschema
from sqlmodel import Session, select

from app import docker_manager, mcp_manager, ollama_manager, webpage_gen, workspace
from app.db import engine
from app.models import Agent, Message
from app.registry import CAPABILITY_OPTIONS

CAPABILITY_LOOKUP = {c.key: c for c in CAPABILITY_OPTIONS}

STEP_NAMES = [
    "Validate configuration",
    "Write agent files",
    "Prepare local model",
    "Start capability servers",
    "Generate interactive webpage",
    "Start container",
    "Health check",
    "Test chat",
    "Test endpoints",
]


def _sample_value(prop_schema: dict):
    if "example" in prop_schema:
        return prop_schema["example"]
    prop_type = prop_schema.get("type", "string")
    return {
        "string": "test",
        "number": 1,
        "integer": 1,
        "boolean": True,
        "array": [],
        "object": {},
    }.get(prop_type, "test")


def _sample_payload(schema: dict) -> dict:
    if "example" in schema:
        return schema["example"]
    properties = schema.get("properties", {})
    return {name: _sample_value(prop) for name, prop in properties.items()}


@dataclass
class BuildStep:
    name: str
    status: str = "pending"  # "pending" | "running" | "success" | "failed"
    detail: Optional[str] = None


@dataclass
class BuildJob:
    id: str
    agent_id: int
    steps: list = field(default_factory=list)
    status: str = "running"  # "running" | "success" | "failed"


_JOBS: dict[str, BuildJob] = {}


def get_job(job_id: str) -> Optional[BuildJob]:
    return _JOBS.get(job_id)


def _is_vision_capable(model_provider: str, model_id: str) -> bool:
    if model_provider == "anthropic":
        return True
    if model_provider == "ollama":
        return model_id == "llava"
    return False


def _validate(agent: Agent) -> Optional[str]:
    if not agent.name or not agent.name.strip():
        return "Agent name is required."
    if not agent.system_prompt or not agent.system_prompt.strip():
        return "No system prompt set. Write one directly or expand a manifesto first."
    if "image_recognition" in agent.capability_keys and not _is_vision_capable(
        agent.model_provider, agent.model_id
    ):
        return (
            "Image Recognition requires a vision-capable model (any Anthropic Claude model, or "
            f"the local LLaVA model) — this agent uses {agent.model_provider}/{agent.model_id}, "
            "which doesn't support image input. Pick a supported model, or remove this capability."
        )
    if agent.model_provider != "ollama" and not agent.model_api_key:
        return (
            f"This agent needs its own {agent.model_provider} API key before it can deploy — "
            "add it on the Review step."
        )
    if agent.model_provider == "ollama":
        mcp_capabilities = [
            CAPABILITY_LOOKUP[key].name
            for key in agent.capability_keys
            if CAPABILITY_LOOKUP.get(key) and CAPABILITY_LOOKUP[key].mcp_server
        ]
        if mcp_capabilities:
            return (
                f"Local Ollama models don't support tool use yet, so {', '.join(mcp_capabilities)} "
                "would never actually run — remove it, or pick a hosted model instead."
            )
    for key in agent.capability_keys:
        capability = CAPABILITY_LOOKUP.get(key)
        if not capability or not capability.requires_api_key:
            continue
        has_own_key = bool(agent.capability_api_keys.get(key))
        has_platform_key = bool(mcp_manager.platform_key_pool(key))
        if not has_own_key and not has_platform_key:
            return (
                f"The {capability.name} capability needs an API key and the platform doesn't have "
                "one configured — add your own on the Capabilities step."
            )
    for job in agent.cron_jobs:
        if not croniter.croniter.is_valid(job["cron_expression"]):
            return f"Invalid cron expression: {job['cron_expression']!r}"
    for ep in agent.endpoints:
        try:
            jsonschema.Draft7Validator.check_schema(ep["input_schema"])
        except jsonschema.SchemaError as exc:
            return f"Invalid input schema for endpoint {ep['path']}: {exc.message}"
    return None


def _fail(job: BuildJob, step: BuildStep, message: str) -> None:
    step.status = "failed"
    step.detail = message
    job.status = "failed"


def _run(job_id: str, agent_id: int) -> None:
    job = _JOBS[job_id]
    with Session(engine) as session:
        agent = session.get(Agent, agent_id)
        if agent is None:
            _fail(job, job.steps[0], "Agent no longer exists.")
            return

        step = job.steps[0]
        step.status = "running"
        error = _validate(agent)
        if error:
            _fail(job, step, error)
            return
        step.status = "success"

        step = job.steps[1]
        step.status = "running"
        try:
            workspace_dir = workspace.ensure_workspace(agent)
        except Exception as exc:  # noqa: BLE001 - surface any write failure to the user
            _fail(job, step, str(exc))
            return
        step.status = "success"

        step = job.steps[2]
        step.status = "running"
        if agent.model_provider == "ollama":
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
            step.detail = "Not needed for this model."

        step = job.steps[3]
        step.status = "running"
        capability_urls: dict[str, str] = {}
        try:
            for key in agent.capability_keys:
                capability = CAPABILITY_LOOKUP.get(key)
                if capability is None or not capability.wired or not capability.mcp_server:
                    continue
                step.detail = f"Starting {capability.name}…"
                capability_urls[key] = mcp_manager.ensure_running(capability.mcp_server)
        except RuntimeError as exc:
            _fail(job, step, f"Capability {key!r} failed to start: {exc}")
            return
        effective_keys = {
            key: agent.capability_api_keys.get(key) or mcp_manager.pick_platform_key(key, agent.id)
            for key in capability_urls
        }
        workspace.write_capabilities(agent, capability_urls, effective_keys)
        step.status = "success"
        step.detail = f"Started: {', '.join(capability_urls)}" if capability_urls else "None needed."

        step = job.steps[4]
        step.status = "running"
        try:
            html = webpage_gen.generate_webpage(agent)
            (workspace_dir / "web" / "index.html").write_text(html)
        except RuntimeError as exc:
            _fail(job, step, str(exc))
            return
        step.status = "success"

        step = job.steps[5]
        step.status = "running"
        step.detail = "Building container image and starting it…"
        try:
            container_id, container_port = docker_manager.deploy(agent, workspace_dir)
        except RuntimeError as exc:
            _fail(job, step, str(exc))
            return
        step.status = "success"
        step.detail = None

        # docker_manager.deploy() already waited for /health internally — this
        # step exists so the user sees it as a distinct, visible checkpoint.
        step = job.steps[6]
        step.status = "running"
        step.status = "success"
        step.detail = f"Container healthy on port {container_port}"

        step = job.steps[7]
        step.status = "running"
        step.detail = "Sending a test message…"
        agent.container_port = container_port
        try:
            reply = docker_manager.chat(
                agent, [{"role": "user", "content": "Say hello in one short sentence."}]
            )
            if not reply.strip():
                raise RuntimeError("Agent replied with empty text.")
        except RuntimeError as exc:
            _fail(job, step, str(exc))
            docker_manager.stop_and_remove(agent)
            return
        step.status = "success"
        step.detail = f"Reply: {reply[:80]}"

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
                    docker_manager.call_endpoint(agent, ep["method"], ep["path"], payload)
                    tested.append(ep["path"])
            except RuntimeError as exc:
                _fail(job, step, str(exc))
                docker_manager.stop_and_remove(agent)
                return
            step.status = "success"
            step.detail = f"Tested: {', '.join(tested)}"

        for message in session.exec(select(Message).where(Message.agent_id == agent_id)).all():
            session.delete(message)
        agent.status = "deployed"
        agent.deployed_at = datetime.utcnow()
        agent.container_id = container_id
        agent.container_port = container_port
        session.add(agent)
        session.commit()
        job.status = "success"


def _run_safely(job_id: str, agent_id: int) -> None:
    job = _JOBS[job_id]
    try:
        _run(job_id, agent_id)
    except Exception as exc:  # noqa: BLE001 - last-resort net: a job must never stay "running"
        # forever just because something unanticipated (rate limits, network
        # errors, ...) blew past every specific except clause below.
        current = next((s for s in job.steps if s.status == "running"), None) or job.steps[0]
        _fail(job, current, f"Unexpected error: {exc}")


def start_build(agent_id: int) -> str:
    job_id = str(uuid.uuid4())
    _JOBS[job_id] = BuildJob(
        id=job_id, agent_id=agent_id, steps=[BuildStep(name=n) for n in STEP_NAMES]
    )
    threading.Thread(target=_run_safely, args=(job_id, agent_id), daemon=True).start()
    return job_id
