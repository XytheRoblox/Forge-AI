from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app import build_pipeline, docker_manager, llm_client, webpage_gen, workspace
from app.db import get_session
from app.models import Agent, Message
from app.schemas import (
    AgentCreate,
    AgentRead,
    AgentUpdate,
    BuildJobRead,
    BuildStartResponse,
    ChatRequest,
    ChatResponse,
    ExpandManifestoRequest,
    ExpandManifestoResponse,
    MessageRead,
    ThemeUpdate,
)

router = APIRouter(prefix="/api/agents", tags=["agents"])


def _get_agent_or_404(agent_id: int, session: Session) -> Agent:
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@router.post("", response_model=AgentRead)
def create_agent(payload: AgentCreate, session: Session = Depends(get_session)):
    agent = Agent(**payload.model_dump())
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return agent


@router.get("", response_model=list[AgentRead])
def list_agents(session: Session = Depends(get_session)):
    return session.exec(select(Agent).order_by(Agent.created_at.desc())).all()


@router.get("/{agent_id}", response_model=AgentRead)
def get_agent(agent_id: int, session: Session = Depends(get_session)):
    return _get_agent_or_404(agent_id, session)


@router.patch("/{agent_id}", response_model=AgentRead)
def update_agent(agent_id: int, payload: AgentUpdate, session: Session = Depends(get_session)):
    agent = _get_agent_or_404(agent_id, session)
    for field, value in payload.model_dump(exclude_unset=True).items():
        # Blank means "leave the stored secret as-is" — the wizard always
        # round-trips these fields but never re-populates them with the
        # existing value, so an empty value never means "clear the key".
        if field in ("model_api_key", "capability_api_keys") and not value:
            continue
        if field == "capability_api_keys":
            setattr(agent, field, {**agent.capability_api_keys, **value})
            continue
        setattr(agent, field, value)
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return agent


@router.delete("/{agent_id}", status_code=204)
def delete_agent(agent_id: int, session: Session = Depends(get_session)):
    agent = _get_agent_or_404(agent_id, session)
    docker_manager.stop_and_remove(agent)
    workspace.remove_workspace(agent_id)
    for message in session.exec(select(Message).where(Message.agent_id == agent_id)).all():
        session.delete(message)
    session.delete(agent)
    session.commit()


@router.post("/{agent_id}/expand-manifesto", response_model=ExpandManifestoResponse)
def expand_manifesto(
    agent_id: int, payload: ExpandManifestoRequest, session: Session = Depends(get_session)
):
    agent = _get_agent_or_404(agent_id, session)
    try:
        system_prompt = llm_client.expand_manifesto(payload.manifesto)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    agent.manifesto = payload.manifesto
    agent.system_prompt = system_prompt
    session.add(agent)
    session.commit()
    return ExpandManifestoResponse(system_prompt=system_prompt)


@router.post("/{agent_id}/build", response_model=BuildStartResponse)
def build_agent(agent_id: int, session: Session = Depends(get_session)):
    _get_agent_or_404(agent_id, session)
    job_id = build_pipeline.start_build(agent_id)
    return BuildStartResponse(job_id=job_id)


@router.get("/{agent_id}/build/{job_id}", response_model=BuildJobRead)
def get_build_status(agent_id: int, job_id: str):
    job = build_pipeline.get_job(job_id)
    if job is None or job.agent_id != agent_id:
        raise HTTPException(status_code=404, detail="Build job not found")
    return job


@router.patch("/{agent_id}/theme", response_model=AgentRead)
def update_theme(agent_id: int, payload: ThemeUpdate, session: Session = Depends(get_session)):
    agent = _get_agent_or_404(agent_id, session)
    agent.theme_color = payload.theme_color
    session.add(agent)
    session.commit()
    session.refresh(agent)
    workspace.write_theme(agent)
    return agent


@router.post("/{agent_id}/stop", response_model=AgentRead)
def stop_agent(agent_id: int, session: Session = Depends(get_session)):
    agent = _get_agent_or_404(agent_id, session)
    docker_manager.stop_and_remove(agent)
    agent.status = "draft"
    agent.container_id = None
    agent.container_port = None
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return agent


@router.post("/{agent_id}/restart", response_model=AgentRead)
def restart_agent(agent_id: int, session: Session = Depends(get_session)):
    """Restart the agent's existing container in place.

    Distinct from stop (which tears the container down and drops the agent
    back to draft) and from build (which re-runs the whole pipeline): this
    keeps the same container and the same workspace, so it's the cheap way to
    recover a wedged agent. The published port changes on restart, so the
    stored port is refreshed from Docker afterwards."""
    agent = _get_agent_or_404(agent_id, session)
    if agent.status != "deployed":
        raise HTTPException(status_code=400, detail="Agent isn't running — deploy it first.")
    try:
        port = docker_manager.restart(agent)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    agent.container_port = port
    session.add(agent)
    session.commit()
    session.refresh(agent)
    return agent


@router.post("/{agent_id}/regenerate-webpage", response_model=AgentRead)
def regenerate_webpage(agent_id: int, session: Session = Depends(get_session)):
    """Rebuild ONLY the agent's chat page, with a freshly generated theme.

    The page lives in the workspace directory that's bind-mounted into the
    container and is re-read from disk on every request, so rewriting the file
    is enough — no image rebuild, no container restart, and the agent keeps
    running and keeps its memory."""
    agent = _get_agent_or_404(agent_id, session)
    workspace_path = workspace.workspace_dir(agent.id)
    try:
        html, theme = webpage_gen.generate_webpage(agent)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    (workspace_path / "web" / "index.html").write_text(html)
    agent.theme_color = theme.get("accent", agent.theme_color)
    session.add(agent)
    session.commit()
    session.refresh(agent)
    workspace.write_theme(agent)
    return agent


@router.get("/{agent_id}/messages", response_model=list[MessageRead])
def get_messages(agent_id: int, session: Session = Depends(get_session)):
    _get_agent_or_404(agent_id, session)
    return session.exec(
        select(Message).where(Message.agent_id == agent_id).order_by(Message.created_at)
    ).all()


@router.post("/{agent_id}/chat", response_model=ChatResponse)
def chat_with_agent(agent_id: int, payload: ChatRequest, session: Session = Depends(get_session)):
    agent = _get_agent_or_404(agent_id, session)
    if agent.status != "deployed":
        raise HTTPException(status_code=400, detail="Agent is not deployed yet.")

    prior = session.exec(
        select(Message).where(Message.agent_id == agent_id).order_by(Message.created_at)
    ).all()

    # The image itself is deliberately not persisted on the Message — the
    # transcript stays text-only, and the note the runtime splices in (either
    # the sidecar's description or a native image block) lives only in the
    # single turn it was uploaded for.
    stored_content = payload.message
    if payload.image:
        stored_content = f"{payload.message}\n\n[image attached]" if payload.message else "[image attached]"
    user_message = Message(agent_id=agent_id, role="user", content=stored_content)
    session.add(user_message)
    session.commit()
    session.refresh(user_message)

    history = [{"role": m.role, "content": m.content} for m in prior]
    history.append({"role": "user", "content": payload.message or "What is in this image?"})

    try:
        reply_text = docker_manager.chat(
            agent, history, image=payload.image.model_dump() if payload.image else None
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    assistant_message = Message(agent_id=agent_id, role="assistant", content=reply_text)
    session.add(assistant_message)
    session.commit()
    session.refresh(assistant_message)

    full_history = session.exec(
        select(Message).where(Message.agent_id == agent_id).order_by(Message.created_at)
    ).all()

    return ChatResponse(reply=assistant_message, history=full_history)
