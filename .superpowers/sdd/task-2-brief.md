### Task 2: Add Featherless Chat Handler to Agent Runtime

**Files:**
- Modify: `backend/agent_runtime/app.py:329-401`
- Modify: `backend/agent_runtime/requirements.txt`

**Interfaces:**
- Consumes: `MODEL_PROVIDER="featherless"`, `MODEL_ID`, `FEATHERLESS_API_KEY` env vars; `_TOOL_INDEX` dict from MCP discovery; `_set_status()`, `_strip_thinking()`, `_execute_tool()` helpers
- Produces: Featherless branch in `_generate_reply()` that returns a string reply after multi-round tool-use loops

- [ ] **Step 1: Add openai to agent runtime requirements**

Change `backend/agent_runtime/requirements.txt` to:

```
fastapi==0.115.6
uvicorn[standard]==0.34.0
anthropic==0.68.0
groq==1.0.0
openai==1.82.0
httpx==0.28.1
jsonschema==4.23.0
croniter==3.0.4
mcp==1.29.0
```

- [ ] **Step 2: Add Featherless client initializer in app.py**

Insert after the `_get_groq()` function (after line 77) in `backend/agent_runtime/app.py`:

```python
_featherless_client = None


def _get_featherless():
    global _featherless_client
    if _featherless_client is None:
        from openai import OpenAI

        api_key = os.environ.get("FEATHERLESS_API_KEY")
        if not api_key:
            raise RuntimeError("FEATHERLESS_API_KEY is not set in this container.")
        _featherless_client = OpenAI(
            base_url="https://api.featherless.ai/v1",
            api_key=api_key,
        )
    return _featherless_client
```

- [ ] **Step 3: Add Featherless branch in _generate_reply()**

Insert after the `elif MODEL_PROVIDER == "groq":` block (after line 401) and before the `elif MODEL_PROVIDER == "ollama":` block in `backend/agent_runtime/app.py`:

```python
    elif MODEL_PROVIDER == "featherless":
        from openai import NOT_GIVEN

        client = _get_featherless()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": info["description"],
                    "parameters": info["input_schema"],
                },
            }
            for name, info in _TOOL_INDEX.items()
        ]
        messages = [{"role": "system", "content": system_prompt}, *history]

        for _ in range(MAX_TOOL_ITERATIONS):
            _set_status(f"Asking {MODEL_ID}…")
            kwargs = {"model": MODEL_ID, "max_tokens": 2048, "messages": messages}
            if tools:
                kwargs["tools"] = tools
            response = client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            if not message.tool_calls:
                _set_status("Writing a reply…")
                return _strip_thinking(message.content or "")

            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in message.tool_calls
                    ],
                }
            )
            for tool_call in message.tool_calls:
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}
                _set_status(f"Using {tool_call.function.name}…")
                result_text = _execute_tool(tool_call.function.name, arguments)
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": result_text})

        _set_status("Writing a final answer…")
        response = client.chat.completions.create(
            model=MODEL_ID, max_tokens=2048, messages=messages
        )
        return _strip_thinking(response.choices[0].message.content or "")
```

- [ ] **Step 4: Verify the Dockerfile doesn't need changes**

Read `backend/agent_runtime/Dockerfile` — it already does `pip install -r requirements.txt` which will pull in `openai`. No change needed.

- [ ] **Step 5: Commit**

```bash
git add backend/agent_runtime/app.py backend/agent_runtime/requirements.txt
git commit -m "feat: add Featherless AI chat handler with tool-use loop in agent runtime"
```

