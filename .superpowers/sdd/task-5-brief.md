### Task 5: Update Data Model and Build Pipeline for Deploy Mode Branching

**Files:**
- Modify: `backend/app/models.py:8-26`
- Modify: `backend/app/schemas.py:52-70`
- Modify: `backend/app/build_pipeline.py:139-272`
- Modify: `frontend/src/types.ts:37-56`
- Modify: `frontend/src/pages/AgentPage.tsx:21`

**Interfaces:**
- Consumes: `cloudrun_manager.deploy_agent()`, `cloudrun_manager.chat()`, `cloudrun_manager.stop_agent()`, `cloudrun_manager.call_endpoint()`
- Produces: `Agent.service_url` field; build pipeline that branches on `DEPLOY_MODE`

- [ ] **Step 1: Add service_url to Agent model**

In `backend/app/models.py`, add after line 26 (`container_port`):

```python
    service_url: Optional[str] = None
    cloudrun_service_name: Optional[str] = None
```

- [ ] **Step 2: Add service_url to AgentRead schema**

In `backend/app/schemas.py`, add after `container_port` (line 70):

```python
    service_url: Optional[str] = None
    cloudrun_service_name: Optional[str] = None
```

- [ ] **Step 3: Update build pipeline to branch on DEPLOY_MODE**

In `backend/app/build_pipeline.py`, replace the `_run` function body (lines 139-272). The key changes are:

Add at the top of the file (after the imports):

```python
DEPLOY_MODE = os.environ.get("DEPLOY_MODE", "local")
```

Add `import os` to the imports at the top.

In the `_run` function, replace the "Prepare local model" step (lines 165-177) with:

```python
        step = job.steps[2]
        step.status = "running"
        if agent.model_provider == "ollama" and DEPLOY_MODE == "local":
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
            step.detail = "Not needed (using API-based inference)."
```

Replace the "Start container" step (lines 209-219) with:

```python
        step = job.steps[5]
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
```

Replace the "Health check" step (lines 222-226) with:

```python
        step = job.steps[6]
        step.status = "running"
        if DEPLOY_MODE == "cloudrun":
            step.status = "success"
            step.detail = f"Service healthy at {service_url}"
        else:
            step.status = "success"
            step.detail = f"Container healthy on port {container_port}"
```

Replace the "Test chat" step (lines 228-241) with:

```python
        step = job.steps[7]
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
```

Replace the "Test endpoints" step (lines 243-262) with:

```python
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
```

Replace the final DB update block (lines 264-272) with:

```python
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
```

- [ ] **Step 4: Update frontend Agent type**

In `frontend/src/types.ts`, add after `container_port` (line 55):

```typescript
  service_url: string | null;
  cloudrun_service_name: string | null;
```

- [ ] **Step 5: Update AgentPage to use service_url for iframe**

In `frontend/src/pages/AgentPage.tsx`, replace line 21:

```typescript
  const webpageUrl = agent.container_port ? `http://localhost:${agent.container_port}/` : null;
```

With:

```typescript
  const webpageUrl = agent.service_url
    ? `${agent.service_url}/`
    : agent.container_port
      ? `http://localhost:${agent.container_port}/`
      : null;
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/app/schemas.py backend/app/build_pipeline.py frontend/src/types.ts frontend/src/pages/AgentPage.tsx
git commit -m "feat: branch build pipeline on DEPLOY_MODE, add service_url to Agent model"
```

