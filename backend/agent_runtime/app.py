import asyncio
import json
import os
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx
import jsonschema
from croniter import croniter
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from mcp import ClientSession
from mcp.client.sse import sse_client
from pydantic import BaseModel

WORKSPACE = Path("/workspace")
MANIFESTO_PATH = WORKSPACE / "MANIFESTO.md"
CACHE_PATH = WORKSPACE / "CACHE.md"
CRON_PATH = WORKSPACE / "CRON.md"
WEBPAGE_PATH = WORKSPACE / "web" / "index.html"
THEME_PATH = WORKSPACE / "theme.json"
ENDPOINTS_PATH = WORKSPACE / "endpoints.json"
CAPABILITIES_PATH = WORKSPACE / "capabilities.json"
FEATURES_PATH = WORKSPACE / "features.json"

CRON_CHECK_INTERVAL_SECONDS = 30
MAX_TOOL_ITERATIONS = 5

# MCP servers are shared across all agents, so a capability that needs its
# own API key (e.g. WolframAlpha) can't have that key baked into the shared
# container's env — instead each agent's own key rides along on every tool
# call. This maps a capability key to the tool argument name that key fills,
# so it can be injected server-side and hidden from the model's tool schema
# entirely (the model should never see or have to fill in an API key).
CAPABILITY_KEY_PARAM = {"wolfram_alpha": "app_id"}

MODEL_PROVIDER = os.environ.get("MODEL_PROVIDER", "anthropic")
MODEL_ID = os.environ.get("MODEL_ID", "claude-sonnet-5")

# Whether this agent's OWN model can accept image input natively. Decided by
# the backend at deploy time (registry.py is the source of truth) rather than
# re-derived here, so the model list only has to be maintained in one place.
MODEL_SUPPORTS_VISION = os.environ.get("MODEL_SUPPORTS_VISION") == "1"

# Vision sidecar: a separate vision-language model that describes uploaded
# images in words, so an agent whose own model is text-only can still "see".
# The image goes to this model, and only its written description is spliced
# into the conversation the agent's real model sees. That keeps image support
# a property of the platform instead of a property of the chosen model — at
# the cost of one extra API call, and of the agent reasoning over a
# description rather than raw pixels (fine detail, exact text, and precise
# spatial layout can be lost). Agents whose model IS natively vision-capable
# skip this entirely and get the real image.
# Tried in order, best-quality first. Featherless is serverless, so any one
# vision model can transiently answer "busy"/"at capacity" — falling back down
# the size ladder keeps image support working instead of failing the turn.
# These are all open-weight Qwen VL models running on the platform's existing
# Featherless plan: no Anthropic/OpenAI call, and no extra paid subscription.
VISION_SIDECAR_MODELS = [
    m.strip()
    for m in os.environ.get(
        "VISION_SIDECAR_MODELS",
        "Qwen/Qwen2.5-VL-72B-Instruct,Qwen/Qwen2.5-VL-32B-Instruct,Qwen/Qwen2.5-VL-7B-Instruct",
    ).split(",")
    if m.strip()
]
VISION_SIDECAR_MAX_TOKENS = 700
VISION_SIDECAR_PROMPT = (
    "Describe this image in thorough, concrete detail so that someone who cannot see it "
    "could answer questions about it. Transcribe any visible text verbatim. Describe "
    "objects, people, colors, layout, and anything notable. Do not speculate about what "
    "is not visible, and do not add commentary — just the description."
)

SYSTEM_PROMPT_FENCE_START = "## System Prompt\n```\n"
SYSTEM_PROMPT_FENCE_END = "\n```\n"
MEMORY_HEADER = "## Memory\n"
NEXT_SECTION_HEADER = "\n## "

app = FastAPI(title="Forge Agent Runtime")

_anthropic_client = None
_groq_client = None


def _get_anthropic():
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import Anthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set in this container.")
        _anthropic_client = Anthropic(api_key=api_key)
    return _anthropic_client


def _get_groq():
    global _groq_client
    if _groq_client is None:
        from groq import Groq

        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("GROQ_API_KEY is not set in this container.")
        _groq_client = Groq(api_key=api_key)
    return _groq_client


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


def _load_system_prompt() -> str:
    if MANIFESTO_PATH.exists():
        text = MANIFESTO_PATH.read_text()
        start = text.find(SYSTEM_PROMPT_FENCE_START)
        if start != -1:
            start += len(SYSTEM_PROMPT_FENCE_START)
            end = text.find(SYSTEM_PROMPT_FENCE_END, start)
            if end != -1:
                return text[start:end]
    return os.environ.get("SYSTEM_PROMPT", "You are a helpful AI agent.")


def _load_memory() -> str:
    if not CACHE_PATH.exists():
        return ""
    text = CACHE_PATH.read_text()
    start = text.find(MEMORY_HEADER)
    if start == -1:
        return ""
    start += len(MEMORY_HEADER)
    end = text.find(NEXT_SECTION_HEADER, start)
    memory = text[start:end if end != -1 else None].strip()
    return "" if memory == "(empty)" else memory


def _effective_system_prompt() -> str:
    base = _load_system_prompt()
    memory = _load_memory()
    if not memory:
        return base
    return f"{base}\n\n## Agent memory (from prior sessions)\n{memory}"


def _append_memory(note: str) -> None:
    if not CACHE_PATH.exists():
        return
    text = CACHE_PATH.read_text()
    start = text.find(MEMORY_HEADER)
    if start == -1:
        return
    start += len(MEMORY_HEADER)
    end = text.find(NEXT_SECTION_HEADER, start)
    before = text[:start]
    after = text[end:] if end != -1 else ""
    current = text[start:end if end != -1 else None].strip()
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    entry = f"- [{timestamp}] {note}"
    new_memory = f"{current}\n{entry}\n" if current and current != "(empty)" else f"{entry}\n"
    CACHE_PATH.write_text(before + new_memory + after)


class ChatImage(BaseModel):
    data: str
    media_type: str


class ChatRequest(BaseModel):
    history: list[dict]
    image: ChatImage | None = None


class ChatResponse(BaseModel):
    reply: str


# What the agent is actually doing right now, mid-reply — polled by the
# chat page's typing indicator so it can show real status ("Using
# ask_wolfram_alpha…") instead of a generic spinner. Plain module-level
# string rather than anything locked/keyed per-request: this container
# serves one agent's chat at a time in practice, so the simplest thing
# that shows real information beats a more "correct" but over-built queue.
_current_status = "idle"


def _set_status(text: str) -> None:
    global _current_status
    _current_status = text


@app.get("/chat/status")
def chat_status():
    return {"status": _current_status}


@app.get("/health")
def health():
    return {"status": "ok", "model_provider": MODEL_PROVIDER, "model_id": MODEL_ID}


def _load_features() -> dict:
    if not FEATURES_PATH.exists():
        return {}
    try:
        return json.loads(FEATURES_PATH.read_text())
    except json.JSONDecodeError:
        return {}


@app.get("/", response_class=HTMLResponse)
def interactive_webpage():
    if not WEBPAGE_PATH.exists():
        return HTMLResponse("<h1>This agent's interactive webpage hasn't been built yet.</h1>")

    html = WEBPAGE_PATH.read_text()
    accent = "#aa3bff"
    if THEME_PATH.exists():
        try:
            accent = json.loads(THEME_PATH.read_text()).get("accent", accent)
        except (json.JSONDecodeError, OSError):
            pass
    html = html.replace("__ACCENT_COLOR__", accent)

    image_upload_enabled = "true" if _load_features().get("image_recognition") else "false"
    html = html.replace("__IMAGE_UPLOAD_ENABLED__", image_upload_enabled)

    return HTMLResponse(html)


def _load_capabilities() -> list[dict]:
    if not CAPABILITIES_PATH.exists():
        return []
    try:
        return json.loads(CAPABILITIES_PATH.read_text())
    except json.JSONDecodeError:
        return []


async def _async_list_tools(mcp_url: str) -> list:
    async with sse_client(mcp_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.list_tools()
            return result.tools


async def _async_call_tool(mcp_url: str, name: str, arguments: dict) -> str:
    async with sse_client(mcp_url) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(name, arguments)
            parts = [block.text for block in result.content if getattr(block, "text", None)]
            return "\n".join(parts) if parts else "(tool returned no output)"


# tool name -> {"mcp_url", "description", "input_schema"}, populated once at
# container startup. A capability whose MCP server isn't reachable yet is
# skipped rather than failing the whole container — chat still works without
# it, just without that tool available.
_TOOL_INDEX: dict[str, dict] = {}


async def _discover_tools() -> None:
    # Runs inside FastAPI's own startup event, which is already async — using
    # asyncio.run() here (or at plain module-import time, before uvicorn's
    # event loop even exists) both fail with "asyncio.run() cannot be called
    # from a running event loop", since uvicorn imports this module from
    # inside its own asyncio.run(Server.serve()).
    for capability in _load_capabilities():
        try:
            tools = await _async_list_tools(capability["mcp_url"])
        except Exception as exc:  # noqa: BLE001 - best-effort discovery, one bad server shouldn't break the rest
            print(f"[capabilities] could not reach {capability['key']}: {exc}")
            continue
        key_param = CAPABILITY_KEY_PARAM.get(capability["key"])
        for tool in tools:
            input_schema = tool.inputSchema
            if key_param and key_param in input_schema.get("properties", {}):
                input_schema = dict(input_schema)
                input_schema["properties"] = {
                    k: v for k, v in input_schema["properties"].items() if k != key_param
                }
                input_schema["required"] = [
                    r for r in input_schema.get("required", []) if r != key_param
                ]
            _TOOL_INDEX[tool.name] = {
                "mcp_url": capability["mcp_url"],
                "description": tool.description or "",
                "input_schema": input_schema,
                "api_key_param": key_param,
                "api_key": capability.get("api_key"),
            }


@app.on_event("startup")
async def _on_startup() -> None:
    await _discover_tools()


def _execute_tool(name: str, arguments: dict) -> str:
    info = _TOOL_INDEX.get(name)
    if info is None:
        return f"Error: unknown tool {name!r}"
    call_args = dict(arguments)
    if info.get("api_key_param") and info.get("api_key"):
        call_args[info["api_key_param"]] = info["api_key"]
    try:
        return asyncio.run(_async_call_tool(info["mcp_url"], name, call_args))
    except Exception as exc:  # noqa: BLE001 - surface the failure to the model, not a 500
        return f"Error calling tool {name!r}: {exc}"


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_thinking(text: str) -> str:
    """Some reasoning models (e.g. Groq's qwen/qwen3.6-27b) emit their chain
    of thought directly in `content` wrapped in <think> tags, rather than in
    a separate `reasoning` field — strip it so it doesn't leak into the
    user-visible chat reply."""
    return _THINK_BLOCK.sub("", text).strip()


def _generate_reply(system_prompt: str, history: list[dict]) -> str:
    if MODEL_PROVIDER == "anthropic":
        client = _get_anthropic()
        tools = [
            {"name": name, "description": info["description"], "input_schema": info["input_schema"]}
            for name, info in _TOOL_INDEX.items()
        ]
        messages = list(history)

        for _ in range(MAX_TOOL_ITERATIONS):
            _set_status(f"Asking {MODEL_ID}…")
            kwargs = {"model": MODEL_ID, "max_tokens": 2048, "system": system_prompt, "messages": messages}
            if tools:
                kwargs["tools"] = tools
            response = client.messages.create(**kwargs)

            if response.stop_reason != "tool_use":
                _set_status("Writing a reply…")
                return "".join(b.text for b in response.content if b.type == "text").strip()

            messages.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})
            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                _set_status(f"Using {block.name}…")
                tool_results.append(
                    {"type": "tool_result", "tool_use_id": block.id, "content": _execute_tool(block.name, block.input)}
                )
            messages.append({"role": "user", "content": tool_results})

        # Ran out of tool-use rounds — ask once more without tools to force a final answer.
        _set_status("Writing a final answer…")
        response = client.messages.create(
            model=MODEL_ID, max_tokens=2048, system=system_prompt, messages=messages
        )
        return "".join(b.text for b in response.content if b.type == "text").strip()

    elif MODEL_PROVIDER == "groq":
        from groq import BadRequestError

        client = _get_groq()
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

        def _call_groq(use_tools: bool):
            kwargs = {"model": MODEL_ID, "max_tokens": 2048, "messages": messages}
            if use_tools and tools:
                kwargs["tools"] = tools
            return client.chat.completions.create(**kwargs)

        for _ in range(MAX_TOOL_ITERATIONS):
            _set_status(f"Asking {MODEL_ID}…")
            try:
                response = _call_groq(use_tools=True)
            except BadRequestError:
                # Some models occasionally emit a malformed tool-call
                # generation that Groq's own validation rejects outright —
                # retry once, then fall back to answering without tools
                # rather than crashing the whole request.
                try:
                    response = _call_groq(use_tools=True)
                except BadRequestError as exc:
                    print(f"[tools] Groq rejected the tool call twice, answering without tools this round: {exc}")
                    response = _call_groq(use_tools=False)
            message = response.choices[0].message

            if not message.tool_calls:
                _set_status("Writing a reply…")
                return _strip_thinking(message.content or "")

            # Build a minimal, request-safe assistant message rather than
            # message.model_dump() — the SDK's response schema includes
            # extra fields (e.g. "annotations") that Groq's own request
            # validation rejects on the next call.
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
        response = _call_groq(use_tools=False)
        return _strip_thinking(response.choices[0].message.content or "")

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

    raise RuntimeError(f"Unsupported model provider: {MODEL_PROVIDER}")


def _describe_image(image: ChatImage) -> str:
    """Runs the vision sidecar over an uploaded image and returns its written
    description. Used only for agents whose own model can't take image input.

    Walks VISION_SIDECAR_MODELS in order and returns the first real answer, so
    a model that's transiently busy on Featherless doesn't take image support
    down with it. Raises only if every candidate fails."""
    client = _get_featherless()
    messages = [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{image.media_type};base64,{image.data}"},
                },
                {"type": "text", "text": VISION_SIDECAR_PROMPT},
            ],
        }
    ]
    last_error: Exception | None = None
    for model in VISION_SIDECAR_MODELS:
        try:
            response = client.chat.completions.create(
                model=model, max_tokens=VISION_SIDECAR_MAX_TOKENS, messages=messages
            )
        except Exception as exc:  # noqa: BLE001 - try the next candidate
            last_error = exc
            continue
        text = _strip_thinking(response.choices[0].message.content or "").strip()
        if text:
            return text
        last_error = RuntimeError(f"{model} returned an empty description")
    raise RuntimeError(f"every vision model failed (last: {last_error})")


def _attach_image_to_history(history: list[dict], image: ChatImage) -> list[dict]:
    """Attaches an uploaded image to the last (newest) user message.

    A natively vision-capable model gets the real image, in whichever shape its
    provider expects — Anthropic wants a multi-part content list with an
    embedded base64 image block, Featherless wants an OpenAI-style `image_url`
    part with a data URI.

    Every other model gets the vision sidecar's written description of the
    image spliced in as plain text, so a text-only agent can still answer
    questions about what was uploaded. If the sidecar itself fails, say so in
    the transcript rather than dropping the image silently — an agent that
    ignores an attachment with no explanation looks broken."""
    if not history or history[-1].get("role") != "user":
        return history

    text = history[-1]["content"]

    if MODEL_SUPPORTS_VISION and MODEL_PROVIDER == "anthropic":
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": image.media_type, "data": image.data}},
            {"type": "text", "text": text},
        ]
        return history[:-1] + [{"role": "user", "content": content}]

    if MODEL_SUPPORTS_VISION and MODEL_PROVIDER == "featherless":
        content = [
            {"type": "image_url", "image_url": {"url": f"data:{image.media_type};base64,{image.data}"}},
            {"type": "text", "text": text},
        ]
        return history[:-1] + [{"role": "user", "content": content}]

    _set_status("Looking at the image…")
    try:
        description = _describe_image(image)
    except Exception as exc:  # noqa: BLE001 - any sidecar failure degrades to a note
        description = ""
        note = f"[The user attached an image, but it could not be read: {exc}]"
    else:
        note = (
            "[The user attached an image. You cannot see it directly, so here is a "
            f"description of it from a vision model:\n{description}\n]"
        )
    if description == "" and "could not be read" not in note:
        note = "[The user attached an image, but no description could be produced for it.]"
    return history[:-1] + [{"role": "user", "content": f"{note}\n\n{text}"}]


@app.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest):
    history = payload.history
    if payload.image:
        history = _attach_image_to_history(history, payload.image)
    _set_status("Reading your message…")
    try:
        try:
            reply = _generate_reply(_effective_system_prompt(), history)
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except Exception as exc:  # noqa: BLE001 - provider SDKs raise their own exception
            # hierarchies (anthropic.AuthenticationError, groq.APIError, ...), none of
            # which are RuntimeError — surface them as a real, readable JSON error
            # instead of letting them fall through to an unhandled-exception response.
            raise HTTPException(status_code=502, detail=f"{type(exc).__name__}: {exc}")
    finally:
        _set_status("idle")
    return ChatResponse(reply=reply)


class CacheUpdateRequest(BaseModel):
    note: str


@app.post("/cache/update")
def update_cache(payload: CacheUpdateRequest):
    _append_memory(payload.note)
    return {"status": "ok"}


def _load_endpoints() -> list[dict]:
    if not ENDPOINTS_PATH.exists():
        return []
    try:
        return json.loads(ENDPOINTS_PATH.read_text())
    except json.JSONDecodeError:
        return []


def _make_endpoint_handler(spec: dict):
    def handler(payload: dict = Body(default={})):
        try:
            jsonschema.validate(payload, spec["input_schema"])
        except jsonschema.ValidationError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid input: {exc.message}")

        prompt = (
            f"{spec['instruction']}\n\n"
            f"Input (JSON): {json.dumps(payload)}\n\n"
            "Respond with just the result — no preamble."
        )
        try:
            reply = _generate_reply(_effective_system_prompt(), [{"role": "user", "content": prompt}])
        except RuntimeError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"output": reply}

    return handler


for _spec in _load_endpoints():
    app.add_api_route(
        _spec["path"],
        _make_endpoint_handler(_spec),
        methods=[_spec["method"]],
    )


def _parse_cron_jobs() -> list[tuple[str, str]]:
    if not CRON_PATH.exists():
        return []
    jobs = []
    for line in CRON_PATH.read_text().splitlines():
        if " :: " not in line:
            continue
        expr, instruction = line.split(" :: ", 1)
        expr = expr.strip()
        if not expr or expr.startswith("#") or expr.startswith("("):
            continue
        try:
            croniter(expr)
        except (ValueError, KeyError):
            continue
        jobs.append((expr, instruction.strip()))
    return jobs


def _cron_loop() -> None:
    last_check = datetime.utcnow()
    while True:
        time.sleep(CRON_CHECK_INTERVAL_SECONDS)
        now = datetime.utcnow()
        for expr, instruction in _parse_cron_jobs():
            try:
                next_fire = croniter(expr, last_check).get_next(datetime)
            except (ValueError, KeyError):
                continue
            if next_fire > now:
                continue
            try:
                reply = _generate_reply(
                    _effective_system_prompt(), [{"role": "user", "content": instruction}]
                )
                _append_memory(f"Cron '{expr}' ran ({instruction[:60]}): {reply[:200]}")
            except RuntimeError as exc:
                _append_memory(f"Cron '{expr}' failed ({instruction[:60]}): {exc}")
        last_check = now


threading.Thread(target=_cron_loop, daemon=True).start()
