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

CRON_CHECK_INTERVAL_SECONDS = 30
MAX_TOOL_ITERATIONS = 5

# MCP servers are shared across all agents, so a capability that needs its
# own API key (e.g. WolframAlpha) can't have that key baked into the shared
# container's env — instead each agent's own key rides along on every tool
# call. This maps a capability key to the tool argument name that key fills,
# so it can be injected server-side and hidden from the model's tool schema
# entirely (the model should never see or have to fill in an API key).
CAPABILITY_KEY_PARAM = {"wolfram_alpha": "app_id"}

MODEL_PROVIDER = os.environ.get("MODEL_PROVIDER", "featherless")
MODEL_ID = os.environ.get("MODEL_ID", "Qwen/Qwen2.5-72B-Instruct")

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
# Featherless plan: no extra paid subscription, and no third-party API.
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
TOOL_LOG_HEADER = "## Tool Call Log\n"
NEXT_SECTION_HEADER = "\n## "

app = FastAPI(title="Forge Agent Runtime")

_groq_client = None


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


def _read_section(header: str) -> str:
    """The body of one `## ` section of CACHE.md, or "" if absent/empty."""
    if not CACHE_PATH.exists():
        return ""
    text = CACHE_PATH.read_text()
    start = text.find(header)
    if start == -1:
        return ""
    start += len(header)
    end = text.find(NEXT_SECTION_HEADER, start)
    body = text[start : end if end != -1 else None].strip()
    return "" if body == "(empty)" else body


def _append_to_section(header: str, entry: str, limit: int) -> None:
    """Append one line to a section, keeping only the newest `limit` lines.

    Creates the section at the end of the file if it isn't there yet, so an
    agent built before a section existed picks it up without a rebuild."""
    if not CACHE_PATH.exists():
        return
    text = CACHE_PATH.read_text()
    start = text.find(header)
    if start == -1:
        text = text.rstrip("\n") + f"\n\n{header}(empty)\n"
        start = text.find(header)
    start += len(header)
    end = text.find(NEXT_SECTION_HEADER, start)
    before, after = text[:start], (text[end:] if end != -1 else "")
    current = text[start : end if end != -1 else None].strip()
    entries = [] if (not current or current == "(empty)") else current.splitlines()
    entries.append(entry)
    entries = [line for line in entries if line.strip()][-limit:]
    CACHE_PATH.write_text(before + "\n".join(entries) + "\n" + after)


def _load_memory() -> str:
    return _read_section(MEMORY_HEADER)


# Every stored memory is replayed into the system prompt on every turn, so an
# unbounded list would grow the prompt without limit and eventually crowd out
# the conversation. Oldest entries are dropped first.
MAX_MEMORY_ENTRIES = 60

# The tool log is working memory, not history: it exists so a multi-step task
# can build on what earlier steps returned. Kept much shorter than memory, and
# each result truncated, because tool output can be enormous.
MAX_TOOL_LOG_ENTRIES = 15
MAX_TOOL_RESULT_CHARS = 600
MAX_TOOL_ARGS_CHARS = 200

MEMORY_INSTRUCTIONS = """

## Memory
You have a `remember` tool that saves a fact to your long-term memory. Memory persists \
across conversations; the chat transcript does not, so anything not saved is lost when the \
conversation ends.

Call `remember` as soon as you learn something durable and worth keeping — the user's name, \
their preferences, their goals, constraints, or decisions you have agreed on — and whenever \
the user asks you to remember something. Save the fact itself as a standalone sentence that \
will still make sense with no surrounding context. Do not save trivia, one-off questions, or \
anything already listed under "Agent memory" below. Never tell the user you will remember \
something without calling the tool in the same turn."""

TOOL_LOG_INSTRUCTIONS = """

## Recent tool calls
Below is a log of the tool calls you have already made, with their arguments and what they \
returned, oldest first. Only the text of your replies survives between turns — the tool \
results themselves do not — so this log is how you keep hold of intermediate results while \
working through a multi-step problem.

Use it: build on values you have already computed or fetched instead of recalculating them, \
and do not repeat an identical call with identical arguments when its result is here already. \
Treat an entry as stale if the user has since changed the inputs, or if it could have changed \
on its own (a time, a price, a live page) — re-run the call in that case."""


def _load_tool_log() -> str:
    return _read_section(TOOL_LOG_HEADER)


def _effective_system_prompt() -> str:
    base = _load_system_prompt()
    # The instructions are unconditional: `remember` is always available, so
    # the prompt must always explain it, whether or not anything is stored yet.
    prompt = f"{base}{MEMORY_INSTRUCTIONS}"
    memory = _load_memory()
    prompt += (
        f"\n\n## Agent memory (from prior sessions)\n{memory}"
        if memory
        else "\n\nYour memory is currently empty."
    )
    # Only described when there's something in it — instructions for reading a
    # log that doesn't exist just invite the model to invent entries.
    tool_log = _load_tool_log()
    if tool_log:
        prompt += f"{TOOL_LOG_INSTRUCTIONS}\n\n{tool_log}"
    return prompt


def _append_memory(note: str) -> None:
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    _append_to_section(MEMORY_HEADER, f"- [{timestamp}] {note}", MAX_MEMORY_ENTRIES)


def _squash(text: str, limit: int) -> str:
    """One-line, length-capped form of a value, so a log entry stays one line."""
    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _log_tool_call(name: str, arguments: dict, result: str) -> None:
    """Record a completed tool call so later turns can build on its result."""
    try:
        args = json.dumps(arguments, ensure_ascii=False)
    except (TypeError, ValueError):
        args = str(arguments)
    timestamp = datetime.utcnow().strftime("%H:%M UTC")
    entry = (
        f"- [{timestamp}] {name}({_squash(args, MAX_TOOL_ARGS_CHARS)}) "
        f"-> {_squash(result, MAX_TOOL_RESULT_CHARS)}"
    )
    _append_to_section(TOOL_LOG_HEADER, entry, MAX_TOOL_LOG_ENTRIES)


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


def _pretty_tool(name: str) -> str:
    """A tool name a person can read.

    MCP tool names are machine identifiers — `ask_wolfram_alpha`,
    `firecrawl_scrape`, `sequential_thinking`. Shown raw in the activity line
    they read as debug output, so underscores become spaces and the redundant
    verb prefixes some servers use are dropped."""
    label = name.replace("_", " ").strip()
    for prefix in ("ask ", "get ", "run "):
        if label.startswith(prefix):
            label = label[len(prefix) :]
            break
    return label or name


@app.get("/chat/status")
def chat_status():
    return {"status": _current_status}


@app.get("/health")
def health():
    return {"status": "ok", "model_provider": MODEL_PROVIDER, "model_id": MODEL_ID}



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

    # Always on. Image support used to be a capability you attached, because it
    # depended on the agent's model being multimodal. Since uploads route
    # through the vision sidecar, every agent can read an image regardless of
    # its model — so hiding the control behind a toggle only creates agents
    # that silently can't be shown a screenshot.
    html = html.replace("__IMAGE_UPLOAD_ENABLED__", "true")

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


# Built-in tools are part of the runtime rather than an MCP capability, so
# they're registered for every agent unconditionally — an agent with no
# capabilities attached still gets memory.
BUILTIN_TOOLS = {
    "remember": {
        "description": (
            "Save a fact to your long-term memory so you still know it in future "
            "conversations. Use it for durable things — the user's name, preferences, "
            "goals, constraints, or agreed decisions — and whenever the user asks you to "
            "remember something."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": (
                        "The fact to remember, as a standalone sentence that will still "
                        "make sense with no surrounding context."
                    ),
                }
            },
            "required": ["note"],
        },
    }
}


def _register_builtin_tools() -> None:
    for name, spec in BUILTIN_TOOLS.items():
        _TOOL_INDEX[name] = {
            "builtin": True,
            "description": spec["description"],
            "input_schema": spec["input_schema"],
        }


def _run_builtin_tool(name: str, arguments: dict) -> str:
    if name == "remember":
        note = (arguments.get("note") or "").strip()
        if not note:
            return "Error: `note` is required and cannot be empty."
        _append_memory(note)
        return f"Saved to memory: {note}"
    return f"Error: unknown built-in tool {name!r}"


@app.on_event("startup")
async def _on_startup() -> None:
    _register_builtin_tools()
    await _discover_tools()


def _execute_tool(name: str, arguments: dict) -> str:
    info = _TOOL_INDEX.get(name)
    if info is None:
        return f"Error: unknown tool {name!r}"
    if info.get("builtin"):
        try:
            return _run_builtin_tool(name, arguments)
        except Exception as exc:  # noqa: BLE001 - report to the model, not a 500
            return f"Error running tool {name!r}: {exc}"
    call_args = dict(arguments)
    if info.get("api_key_param") and info.get("api_key"):
        call_args[info["api_key_param"]] = info["api_key"]
    try:
        result = asyncio.run(_async_call_tool(info["mcp_url"], name, call_args))
    except Exception as exc:  # noqa: BLE001 - surface the failure to the model, not a 500
        result = f"Error calling tool {name!r}: {exc}"
    # Logged from here rather than from each provider's loop so every path —
    # chat, custom endpoints, cron — records calls the same way. Failures are
    # logged too: knowing a call already failed is what stops the model
    # retrying it identically. The API key is deliberately logged from
    # `arguments`, not `call_args`, so an injected secret never lands on disk.
    _log_tool_call(name, arguments, result)
    return result


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_thinking(text: str) -> str:
    """Some reasoning models (e.g. Groq's qwen/qwen3.6-27b) emit their chain
    of thought directly in `content` wrapped in <think> tags, rather than in
    a separate `reasoning` field — strip it so it doesn't leak into the
    user-visible chat reply."""
    return _THINK_BLOCK.sub("", text).strip()


def _generate_reply(system_prompt: str, history: list[dict]) -> str:
    if MODEL_PROVIDER == "groq":
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

        for round_index in range(MAX_TOOL_ITERATIONS):
            _set_status("Thinking…")
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
            # Not every model returns an id with its tool calls — Mistral
            # Medium returns null — but the API rejects the follow-up request
            # if the assistant message or the tool result carries a null id
            # (422 on messages.N.tool_calls.0.id). Synthesize one in that case
            # so the second round of the loop still goes through; the id only
            # has to correlate a call with its result.
            #
            # The exact shape matters: Mistral additionally requires ids to be
            # 9 alphanumeric characters ("Tool call id ... must be a-z, A-Z,
            # 0-9, with a length of 9"), so this pads to precisely that rather
            # than using a readable "call_1".
            call_ids = [
                tc.id or f"c{round_index:02d}{position:02d}0000"
                for position, tc in enumerate(message.tool_calls)
            ]
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for call_id, tc in zip(call_ids, message.tool_calls)
                    ],
                }
            )
            for call_id, tool_call in zip(call_ids, message.tool_calls):
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}
                _set_status(f"Contacting {_pretty_tool(tool_call.function.name)}…")
                result_text = _execute_tool(tool_call.function.name, arguments)
                messages.append({"role": "tool", "tool_call_id": call_id, "content": result_text})

        _set_status("Writing the answer…")
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

        for round_index in range(MAX_TOOL_ITERATIONS):
            _set_status("Thinking…")
            kwargs = {"model": MODEL_ID, "max_tokens": 2048, "messages": messages}
            if tools:
                kwargs["tools"] = tools
            response = client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            if not message.tool_calls:
                _set_status("Writing a reply…")
                return _strip_thinking(message.content or "")

            # Not every model returns an id with its tool calls — Mistral
            # Medium returns null — but the API rejects the follow-up request
            # if the assistant message or the tool result carries a null id
            # (422 on messages.N.tool_calls.0.id). Synthesize one in that case
            # so the second round of the loop still goes through; the id only
            # has to correlate a call with its result.
            #
            # The exact shape matters: Mistral additionally requires ids to be
            # 9 alphanumeric characters ("Tool call id ... must be a-z, A-Z,
            # 0-9, with a length of 9"), so this pads to precisely that rather
            # than using a readable "call_1".
            call_ids = [
                tc.id or f"c{round_index:02d}{position:02d}0000"
                for position, tc in enumerate(message.tool_calls)
            ]
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for call_id, tc in zip(call_ids, message.tool_calls)
                    ],
                }
            )
            for call_id, tool_call in zip(call_ids, message.tool_calls):
                try:
                    arguments = json.loads(tool_call.function.arguments)
                except json.JSONDecodeError:
                    arguments = {}
                _set_status(f"Contacting {_pretty_tool(tool_call.function.name)}…")
                result_text = _execute_tool(tool_call.function.name, arguments)
                messages.append({"role": "tool", "tool_call_id": call_id, "content": result_text})

        _set_status("Writing the answer…")
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

    A natively vision-capable model gets the real image as an OpenAI-style
    `image_url` part with a data URI.

    Every other model gets the vision sidecar's written description of the
    image spliced in as plain text, so a text-only agent can still answer
    questions about what was uploaded. If the sidecar itself fails, say so in
    the transcript rather than dropping the image silently — an agent that
    ignores an attachment with no explanation looks broken."""
    if not history or history[-1].get("role") != "user":
        return history

    text = history[-1]["content"]

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
            # hierarchies (openai.AuthenticationError, groq.APIError, ...), none of
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
