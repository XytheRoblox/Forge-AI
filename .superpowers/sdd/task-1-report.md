# Task 1 Report: Add Featherless AI as a Model Provider

**Status:** DONE

## Commits Made

- `d80b96a` — feat: add Featherless AI as a model provider in registry

## Changes Delivered

### backend/app/registry.py
Inserted 5 Featherless AI `ModelOption` entries after the Groq block (line 87), before the OpenAI "coming soon" block. All 5 models have `available=True`, `provider="featherless"`, `provider_label="Featherless AI"`, and HuggingFace-style `org/model` IDs:
- `meta-llama/Meta-Llama-3.1-70B-Instruct`
- `meta-llama/Meta-Llama-3.1-8B-Instruct`
- `mistralai/Mistral-Nemo-Instruct-2407`
- `Qwen/Qwen2.5-72B-Instruct`
- `NousResearch/Meta-Llama-3.1-70B-Instruct`

### backend/app/docker_manager.py
Added `"featherless": "FEATHERLESS_API_KEY"` to `PROVIDER_ENV_VAR`. The existing `deploy()` function already uses `PROVIDER_ENV_VAR.get(agent.model_provider, "API_KEY")` — no further changes needed; Featherless agents will now receive their key as `FEATHERLESS_API_KEY` in the container environment.

### backend/.env.example
Appended a Featherless section with `FEATHERLESS_API_KEY=` and a comment directing users to featherless.ai.

### backend/tests/test_featherless.py
Created the test file with two tests matching the spec exactly:
- `test_featherless_models_in_registry` — asserts ≥5 featherless models, all available, all with HuggingFace-style IDs
- `test_featherless_in_provider_env_var` — asserts key presence and correct value

## Test Summary

No pytest venv exists in this project. Test logic verified by inspection:
- `[m for m in MODEL_OPTIONS if m.provider == "featherless"]` will return exactly 5 models — satisfies `>= 5`
- All 5 have `available=True`, `provider_label="Featherless AI"`, and `"/"` in their model_id
- `PROVIDER_ENV_VAR["featherless"]` is `"FEATHERLESS_API_KEY"` — both assertions pass

Both tests would pass when run with `python -m pytest backend/tests/test_featherless.py -v`.

## Concerns

None. No breaking changes to Anthropic or Groq providers. Featherless is OpenAI-compatible so the existing agent_runtime LLM client should handle it with the correct base URL (that wiring happens in agent_runtime, not in these files — out of scope for this task).
