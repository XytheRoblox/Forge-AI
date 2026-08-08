### Task 1: Add Featherless AI as a Model Provider

**Files:**
- Modify: `backend/app/registry.py:3-256`
- Modify: `backend/app/docker_manager.py:13-15`
- Modify: `backend/.env.example`
- Create: `backend/tests/test_featherless.py`

**Interfaces:**
- Consumes: existing `ModelOption` schema from `backend/app/schemas.py`
- Produces: `featherless` entries in `MODEL_OPTIONS` list; `"featherless": "FEATHERLESS_API_KEY"` in `PROVIDER_ENV_VAR`

- [ ] **Step 1: Add Featherless models to registry.py**

Insert after the Groq models block (line 78) and before the OpenAI block (line 87):

```python
    # --- Featherless AI — OpenAI-compatible serverless inference, needs FEATHERLESS_API_KEY ---
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="meta-llama/Meta-Llama-3.1-70B-Instruct",
        label="Llama 3.1 70B Instruct",
        description="Meta's flagship open model on Featherless — strong reasoning and tool use, serverless GPU inference.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="meta-llama/Meta-Llama-3.1-8B-Instruct",
        label="Llama 3.1 8B Instruct",
        description="Fast and capable smaller Llama model on Featherless. Good for simple agents where speed matters.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="mistralai/Mistral-Nemo-Instruct-2407",
        label="Mistral Nemo 12B",
        description="Mistral's efficient mid-size model on Featherless. Good balance of speed and capability.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="Qwen/Qwen2.5-72B-Instruct",
        label="Qwen 2.5 72B",
        description="Alibaba's large multilingual model on Featherless. Strong at coding and multilingual tasks.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="NousResearch/Meta-Llama-3.1-70B-Instruct",
        label="Nous Llama 3.1 70B",
        description="Nous Research's fine-tune of Llama 3.1 70B on Featherless. Enhanced instruction following.",
        available=True,
    ),
```

- [ ] **Step 2: Add featherless to PROVIDER_ENV_VAR in docker_manager.py**

Change line 13-15 of `backend/app/docker_manager.py` from:

```python
PROVIDER_ENV_VAR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
}
```

To:

```python
PROVIDER_ENV_VAR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "groq": "GROQ_API_KEY",
    "featherless": "FEATHERLESS_API_KEY",
}
```

- [ ] **Step 3: Update .env.example with Featherless key**

Append to `backend/.env.example`:

```bash

# Featherless AI — serverless GPU inference for open-source models.
# Each agent can supply their own key via the wizard; this is the platform fallback.
# Sign up at featherless.ai to get an API key.
FEATHERLESS_API_KEY=
```

- [ ] **Step 4: Write test for registry additions**

Create `backend/tests/test_featherless.py`:

```python
from app.registry import MODEL_OPTIONS
from app.docker_manager import PROVIDER_ENV_VAR


def test_featherless_models_in_registry():
    featherless_models = [m for m in MODEL_OPTIONS if m.provider == "featherless"]
    assert len(featherless_models) >= 5
    for model in featherless_models:
        assert model.available is True
        assert model.provider_label == "Featherless AI"
        assert "/" in model.model_id  # HuggingFace-style org/model format


def test_featherless_in_provider_env_var():
    assert "featherless" in PROVIDER_ENV_VAR
    assert PROVIDER_ENV_VAR["featherless"] == "FEATHERLESS_API_KEY"
```

- [ ] **Step 5: Run tests**

Run: `cd /Users/arvindsr/Forge/backend && python -m pytest tests/test_featherless.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: Commit**

```bash
git add backend/app/registry.py backend/app/docker_manager.py backend/.env.example backend/tests/test_featherless.py
git commit -m "feat: add Featherless AI as a model provider in registry"
```

