import os
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import croniter
import jsonschema
from sqlmodel import Session, select

from app import docker_manager, mcp_manager, registry, webpage_gen, workspace
from app.db import engine
from app.models import Agent, Message
from app.registry import CAPABILITY_OPTIONS

DEPLOY_MODE = os.environ.get("DEPLOY_MODE", "local")
CAPABILITY_LOOKUP = {c.key: c for c in CAPABILITY_OPTIONS}

STEP_NAMES = [
    "Validate configuration",
    "Write agent files",
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


def _validate(agent: Agent) -> Optional[str]:
    if not agent.name or not agent.name.strip():
        return "Agent name is required."
    if not agent.system_prompt or not agent.system_prompt.strip():
        return "No system prompt set. Write one directly or expand a manifesto first."
    # Image Recognition deliberately has no model requirement: models that
    # can't take image input get uploads described by the vision sidecar
    # instead (see agent_runtime/app.py), so every agent can use it. The
    # sidecar runs on Featherless, though, so a platform key has to exist for
    # any agent that isn't already carrying one of its own.
    if (
        "image_recognition" in agent.capability_keys
        and not registry.supports_vision(agent.model_provider, agent.model_id)
        and not os.environ.get("FEATHERLESS_API_KEY")
    ):
        return (
            f"Image Recognition on {agent.model_provider}/{agent.model_id} needs the vision "
            "sidecar, which runs on Featherless — but the platform has no FEATHERLESS_API_KEY "
            "configured. Add one to backend/.env, or pick a model that reads images natively."
        )
    if not agent.model_api_key:
        if agent.model_provider == "featherless" and os.environ.get("FEATHERLESS_API_KEY"):
            pass
        else:
            return (
                f"This agent needs its own {agent.model_provider} API key before it can deploy — "
                "add it on the Review step."
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

        step = job.steps[3]
        step.status = "running"
        try:
            html = webpage_gen.generate_webpage(agent)
            (workspace_dir / "web" / "index.html").write_text(html)
        except RuntimeError as exc:
            _fail(job, step, str(exc))
            return
        step.status = "success"

        step = job.steps[4]
        step.status = "running"
        if DEPLOY_MODE == "cloudrun":
            step.detail = "Deploying to Cloud Run…"
            try:
                from app import cloudrun_manager
                service_name, service_url = cloudrun_manager.deploy_agent(agent, workspace_dir)
            except RuntimeError as exc:
                _fail(job, step, str(exc))
                return
            step.status = "success"
            step.detail = f"Deployed: {service_url}"
        else:
            step.detail = "Building container image and starting it…"
            try:
                container_id, container_port = docker_manager.deploy(agent, workspace_dir)
            except RuntimeError as exc:
                _fail(job, step, str(exc))
                return
            step.status = "success"
            step.detail = None

        # deploy() already waited for /health internally — this step exists so
        # the user sees it as a distinct, visible checkpoint.
        step = job.steps[5]
        step.status = "running"
        if DEPLOY_MODE == "cloudrun":
            step.status = "success"
            step.detail = f"Service healthy at {service_url}"
        else:
            step.status = "success"
            step.detail = f"Container healthy on port {container_port}"

        step = job.steps[6]
        step.status = "running"
        step.detail = "Sending a test message…"
        if DEPLOY_MODE == "cloudrun":
            agent.service_url = service_url
            try:
                reply = cloudrun_manager.chat(
                    agent, [{"role": "user", "content": "Say hello in one short sentence."}]
                )
            except RuntimeError as exc:
                _fail(job, step, str(exc))
                cloudrun_manager.stop_agent(agent)
                return
        else:
            agent.container_port = container_port
            try:
                reply = docker_manager.chat(
                    agent, [{"role": "user", "content": "Say hello in one short sentence."}]
                )
            except RuntimeError as exc:
                _fail(job, step, str(exc))
                docker_manager.stop_and_remove(agent)
                return
        if not reply.strip():
            _fail(job, step, "Agent replied with empty text.")
            return
        step.status = "success"
        step.detail = f"Reply: {reply[:80]}"

        step = job.steps[7]
        step.status = "running"
        if not agent.endpoints:
            step.status = "success"
            step.detail = "No custom endpoints configured."
        else:
            tested = []
            try:
                for ep in agent.endpoints:
                    payload = _sample_payload(ep["input_schema"])
                    if DEPLOY_MODE == "cloudrun":
                        cloudrun_manager.call_endpoint(agent, ep["method"], ep["path"], payload)
                    else:
                        docker_manager.call_endpoint(agent, ep["method"], ep["path"], payload)
                    tested.append(ep["path"])
            except RuntimeError as exc:
                _fail(job, step, str(exc))
                if DEPLOY_MODE == "cloudrun":
                    cloudrun_manager.stop_agent(agent)
                else:
                    docker_manager.stop_and_remove(agent)
                return
            step.status = "success"
            step.detail = f"Tested: {', '.join(tested)}"

        for message in session.exec(select(Message).where(Message.agent_id == agent_id)).all():
            session.delete(message)
        agent.status = "deployed"
        agent.deployed_at = datetime.utcnow()
        if DEPLOY_MODE == "cloudrun":
            agent.cloudrun_service_name = service_name
            agent.service_url = service_url
        else:
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
