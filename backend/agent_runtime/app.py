import asyncio
from contextlib import asynccontextmanager
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
from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
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
# A decomposed problem spends one round per sub-result — find the components,
# solve for the time, then compute the distance — so a cap of 5 silently
# truncated exactly the multi-step work the tools exist for. The loop still
# exits as soon as the model stops asking for tools; this only raises the
# ceiling for problems that genuinely need the rounds.
MAX_TOOL_ITERATIONS = 10

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

# What a tool result is allowed to contribute to the PROMPT. Scrapers and file
# readers return whole documents — a single Firecrawl page can be tens of
# thousands of tokens — and the full result was being appended to the
# conversation untruncated, so one scrape could blow past the model's context
# limit and fail the turn outright. The model gets the top of the result,
# which is where the answer almost always is, plus a marker so it knows the
# text was cut rather than assuming it saw everything.
MAX_TOOL_RESULT_TO_MODEL = 8000

# Ceiling on the ENTIRE prompt, not any single part of it. Per-item caps are
# not enough on their own: with ten tool rounds allowed, ten individually
# reasonable results still add up past the window. Roughly 4 chars per token,
# so ~22k tokens — deliberately well under a 32k limit, because the limit
# covers the reply too, and an overshoot is a hard 400 rather than a
# degradation.
MAX_PROMPT_CHARS = int(os.environ.get("MAX_PROMPT_CHARS", "88000"))

# Interim narration is only worth showing when the final message can't stand
# on its own. Keeping it unconditionally was worse than the problem it fixed:
# a model that says "Let me try a different approach:" before each of six tool
# calls produced six such fragments stitched together, with the actual results
# invisible between them. Below this length the final message reads as a stub
# — "Final answer: 67.2 m" — and the working is worth restoring; above it, the
# model has already written its own answer and the fragments are noise.
STUB_REPLY_CHARS = 220

# What an older tool result is squeezed to when the prompt has to shrink. The
# most recent results are what the model is actively reasoning about; earlier
# ones usually only need to be remembered in outline.
SHRUNK_TOOL_RESULT_CHARS = 700
KEEP_FULL_TOOL_RESULTS = 2

# Ceiling on replayed conversation. Transcripts only grow, so without this an
# agent works fine for a week and then starts failing on every message with no
# change in what the user is doing.
MAX_HISTORY_CHARS = 40000

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

REASONING_INSTRUCTIONS = """

## How to work a problem
Before answering anything that takes more than one step, plan it out:

1. Say what is being asked and what you were given.
2. Break it into sub-problems, and name them. Solve them in dependency order — a value you
   need later is a sub-problem you do first.
3. For each sub-problem, decide whether you need a tool at all. Setting up the physics,
   choosing the method, deciding which formula applies, and interpreting the result are your
   job and no tool does them for you.
4. Solve, then sanity-check the answer: right order of magnitude, right units, right sign,
   and consistent with the situation described.

Use a computational tool for the parts that are genuinely computational — evaluating an
integral, solving an equation, arithmetic you could get wrong — and give each call ONE
well-posed sub-problem, already reduced to symbols. One sub-problem per call is about how to
pose a call, not how many you may make at once: sub-problems that don't depend on each other
should be requested TOGETHER in a single step, and only chained when a later one genuinely
needs an earlier result. Don't hand it the original word problem
and hope: it can't see the setup you're carrying in your head, and a confident wrong answer
to a badly-posed query is worse than no tool at all. Cite what you got back and carry it into
the next step.

Some questions need no tool whatsoever. Conceptual questions — which force is larger, what
happens qualitatively, why a result looks the way it does — are answered by reasoning about
the situation, and reaching for a calculator instead of thinking is how those get answered
wrongly. In particular, be careful with a system that is momentarily at rest: zero velocity
does not mean zero acceleration, and it does not mean the forces balance.

If a tool's answer contradicts your own reasoning, don't just adopt it. Work out which is
wrong and say so.

## When a tool fails
Say so plainly, name the tool, quote what it reported, and say what the user can do about it —
a permission error usually means the connected account needs reconnecting with more access.
Then stop.

Do not paper over a failure. If you were asked to work with the user's real data and couldn't
reach it, substituting a generic explanation of the topic is not a partial answer; it looks
like you succeeded while quietly answering a different question. One or two sentences naming
the problem beats a page of material nobody asked for.

Retry a failed call only if you are changing something specific about it. Trying the same
call again, or trying three other tools in the hope one works, wastes the user's time and
buries the actual error."""


PLANNING_INSTRUCTIONS = """

## Planning before acting
You have a `sequentialthinking` tool. Use it at the START of any task needing more than one
tool call, to think the whole approach through in one pass before touching anything else.

In that plan, work out and name every call you intend to make, what each is for, and which
of them depend on the results of others. Then act on the plan rather than re-deriving it:

- Issue every independent call together in a single step. Four unrelated lookups are one
  step, not four.
- Chain a call after another only where it truly needs the earlier result.
- Don't return to `sequentialthinking` after each result. Go back to it only when a result
  genuinely invalidates the plan — a lookup that failed, or an answer that contradicts what
  you assumed. Re-planning after every step is the slow, expensive habit this tool exists to
  replace.

Thinking is not free either: plan once, in as few thoughts as the problem honestly needs."""

TOOL_LOG_INSTRUCTIONS = """

## Recent tool calls
Below is a log of the tool calls you have already made, with their arguments and what they \
returned, oldest first. Only the text of your replies survives between turns — the tool \
results themselves do not — so this log is how you keep hold of intermediate results while \
working through a multi-step problem.

Use it: build on values you have already computed or fetched instead of recalculating them, \
and do not repeat an identical call with identical arguments when its result is here already. \
Treat an entry as stale if the user has since changed the inputs, or if it could have changed \
on its own (a time, a price, a live page) — re-run the call in that case.

Only successful calls are recorded here. A call missing from this log may simply have failed \
earlier; that is not a reason to avoid trying it now, since whatever blocked it may have been \
fixed since."""


def _load_tool_log() -> str:
    return _read_section(TOOL_LOG_HEADER)


def _effective_system_prompt() -> str:
    base = _load_system_prompt()
    # The instructions are unconditional: `remember` is always available, so
    # the prompt must always explain it, whether or not anything is stored yet.
    # Reasoning guidance comes before the memory section: it's about how to
    # answer at all, which applies to every turn, whereas memory is context for
    # a particular one.
    prompt = f"{base}{REASONING_INSTRUCTIONS}"
    # Described only when the agent actually has it. Instructions for a tool
    # that isn't attached invite the model to call something that doesn't
    # exist and spend a round finding out.
    if "sequentialthinking" in _TOOL_INDEX:
        prompt += PLANNING_INSTRUCTIONS
    prompt += MEMORY_INSTRUCTIONS
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


class ToolUse(BaseModel):
    round: int = 0
    name: str
    ok: bool
    icon: str = ""
    # The exact request the model made and what came back, so a reply's tool
    # use can be inspected rather than taken on trust. `args` is the model's
    # OWN arguments, captured before the platform injects an API key — a
    # panel the user can open must never be able to show a secret.
    tool: str = ""
    args: str = ""
    result: str = ""
    # The capability this tool belongs to. The page matches logos on this
    # rather than on `name`, so renaming a capability never silently drops
    # its mark.
    key: str = ""


class ChatResponse(BaseModel):
    reply: str
    # Which tools this particular turn used, in call order, so the page can
    # show its work. Empty when the model answered without reaching for
    # anything.
    tools: list[ToolUse] = []


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


# FastAPI runs these sync endpoints in a threadpool, so concurrent chats are
# concurrent THREADS. A module-level list would interleave one conversation's
# tool calls into another's reply; thread-local state keeps each turn's record
# to itself.
_turn = threading.local()


def _begin_turn() -> None:
    _turn.tools = []
    _turn.round = 0
    _turn.attachments = []


# What a detail panel shows. Generous next to the tool log's 600 — this is
# read deliberately by someone who opened it, not replayed into every prompt.
MAX_UI_RESULT_CHARS = 2000


def _clip(text: str, limit: int) -> str:
    text = str(text)
    return text if len(text) <= limit else text[:limit].rstrip() + f"\n… (+{len(text) - limit} more characters)"


def _record_tool_use(name: str, ok: bool, arguments: dict, result: str) -> None:
    calls = getattr(_turn, "tools", None)
    if calls is None:
        return
    info = _TOOL_INDEX.get(name) or {}
    try:
        args = json.dumps(arguments, indent=2, ensure_ascii=False)
    except (TypeError, ValueError):
        args = str(arguments)
    calls.append(
        {
            # Which round of the tool loop this call belongs to. Calls sharing
            # a round were issued together in one request, which is the
            # difference between an agent that planned and one that is
            # discovering its next step each time.
            "round": getattr(_turn, "round", 0),
            "name": info.get("label") or _pretty_tool(name),
            "icon": info.get("icon") or "",
            "key": info.get("capability_key") or "",
            "ok": ok,
            # The identifier is worth surfacing even though the chip shows the
            # brand: one capability exposes several tools, and which one ran is
            # exactly what someone opening this panel wants to know.
            "tool": name,
            "args": _clip(args, MAX_UI_RESULT_CHARS),
            "result": _clip(result, MAX_UI_RESULT_CHARS),
        }
    )


def _turn_tools() -> list[dict]:
    return list(getattr(_turn, "tools", []) or [])


# Markdown images a tool produced this turn. A generated image is the ANSWER,
# but the model routinely describes it instead of repeating the markdown —
# "Here's a textbook-style illustration…" with no illustration. Whether the
# user sees what was made shouldn't depend on the model choosing to quote a
# URL, so anything a tool rendered is re-attached to the reply if it's missing.
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\((https?://[^)\s]+)\)")
_RENDERABLE_BLOCK = re.compile(r"```(?:desmos)\s*[\s\S]*?```")


def _collect_attachments(result: str) -> None:
    """Remember anything a tool produced that the page can RENDER.

    A generated image or a graph spec is the answer itself, not a description
    of one — but the model routinely paraphrases instead of repeating it
    ("Here's a textbook-style illustration…", with no illustration). Whether
    the user sees what was made shouldn't depend on the model choosing to
    quote it back."""
    holder = getattr(_turn, "attachments", None)
    if holder is None:
        return
    for pattern in (_MARKDOWN_IMAGE, _RENDERABLE_BLOCK):
        for match in pattern.finditer(result or ""):
            if match.group(0) not in holder:
                holder.append(match.group(0))


def _fingerprint(attachment: str) -> str:
    """The part of an attachment that identifies it inside a reply — the URL
    for an image, the whole block otherwise."""
    if attachment.startswith("!["):
        return attachment.split("](", 1)[-1].rstrip(")")
    return attachment


def _with_attachments(reply: str) -> str:
    missing = [
        attachment
        for attachment in getattr(_turn, "attachments", []) or []
        if _fingerprint(attachment) not in reply
    ]
    if not missing:
        return reply
    return "\n\n".join([reply.strip(), *missing]).strip()


def _tool_label(name: str) -> str:
    """The brand a person recognises, falling back to a tidied identifier."""
    info = _TOOL_INDEX.get(name) or {}
    return info.get("label") or _pretty_tool(name)


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


@asynccontextmanager
async def _mcp_session(capability: dict):
    """An initialised MCP session for a capability, over whichever transport
    it uses.

    stdio means this container runs the server itself as a subprocess — which
    is what lets an agent hold its OWN credential, since the process inherits
    this agent's environment rather than a shared container's. sse means a
    capability container shared across agents, still used for servers too
    heavy or too stateful to run per agent.

    The process is started and torn down around each use. That costs a spawn
    per call, but keeps a wedged server from outliving the request that
    wedged it, and matches how the SSE path already behaves."""
    if capability.get("transport") == "stdio":
        params = StdioServerParameters(
            command=capability["command"],
            args=capability.get("args") or [],
            # Inherit this container's environment and layer the capability's
            # own credential on top, so the subprocess sees exactly what it
            # needs and nothing is shared between agents.
            env={**os.environ, **(capability.get("env") or {})},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                yield session
        return

    async with sse_client(capability["mcp_url"]) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


async def _async_list_tools(capability: dict) -> list:
    async with _mcp_session(capability) as session:
        result = await session.list_tools()
        return result.tools


async def _async_call_tool(capability: dict, name: str, arguments: dict) -> str:
    async with _mcp_session(capability) as session:
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
            tools = await _async_list_tools(capability)
        except Exception as exc:  # noqa: BLE001 - best-effort discovery, one bad server shouldn't break the rest
            print(f"[capabilities] could not reach {capability['key']}: {exc}")
            continue
        key_param = CAPABILITY_KEY_PARAM.get(capability["key"])
        # Several capabilities can share one server process (every Google one
        # does). When a capability declares which tools are its own, ignore the
        # rest — otherwise whichever is discovered last relabels them all.
        owned = capability.get("tools")
        for tool in tools:
            if owned and tool.name not in owned:
                continue
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
                "capability": capability,
                "description": tool.description or "",
                "input_schema": input_schema,
                "api_key_param": key_param,
                "api_key": capability.get("api_key"),
                # What a person should see when this tool runs: the
                # capability's brand, not the MCP identifier. A single
                # capability often exposes several tools (firecrawl_scrape,
                # firecrawl_search), and naming each one separately turns one
                # action into a wall of unfamiliar strings.
                "label": capability.get("label") or _pretty_tool(tool.name),
                "icon": capability.get("icon") or "",
                "capability_key": capability.get("key") or "",
            }


# Built-in tools are part of the runtime rather than an MCP capability, so
# they're registered for every agent unconditionally — an agent with no
# capabilities attached still gets memory.
BUILTIN_TOOLS = {
    "remember": {
        "label": "Memory",
        "icon": "\U0001F9E0",
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
            "label": spec["label"],
            "icon": spec["icon"],
            "capability_key": name,
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


def _trim_history(history: list[dict]) -> list[dict]:
    """The most recent turns that fit the budget, oldest dropped first.

    Kept whole-message: cutting a message in half leaves the model reading a
    sentence that stops mid-clause and treating it as fact."""
    kept: list[dict] = []
    budget = MAX_HISTORY_CHARS
    for message in reversed(history):
        size = len(str(message.get("content") or ""))
        if kept and size > budget:
            break
        kept.append(message)
        budget -= size
    return list(reversed(kept))


def _message_size(message: dict) -> int:
    size = len(str(message.get("content") or ""))
    for call in message.get("tool_calls") or []:
        size += len(json.dumps(call))
    return size


def _fit_to_budget(messages: list[dict]) -> list[dict]:
    """Bring a conversation under MAX_PROMPT_CHARS, losing the least useful
    material first.

    Order matters. Older tool output is shrunk before anything is dropped,
    because a scraped page the model has already summarised is the cheapest
    thing to lose. Only if that isn't enough are whole turns dropped from the
    front — and never the system prompt or the newest turn, which are what the
    reply is actually built from.

    Returning something slightly over budget is better than returning
    something incoherent, so this stops rather than stripping the request bare.
    """
    total = sum(_message_size(m) for m in messages)
    if total <= MAX_PROMPT_CHARS:
        return messages

    trimmed = [dict(m) for m in messages]
    tool_positions = [i for i, m in enumerate(trimmed) if m.get("role") == "tool"]
    for i in tool_positions[:-KEEP_FULL_TOOL_RESULTS] if KEEP_FULL_TOOL_RESULTS else tool_positions:
        content = str(trimmed[i].get("content") or "")
        if len(content) > SHRUNK_TOOL_RESULT_CHARS:
            trimmed[i]["content"] = _clip(content, SHRUNK_TOOL_RESULT_CHARS)
    total = sum(_message_size(m) for m in trimmed)
    if total <= MAX_PROMPT_CHARS:
        return trimmed

    # Still too big: drop the oldest turns. Index 0 is the system prompt and
    # the last message is the live one, so both stay.
    head, tail = trimmed[0], trimmed[-1]
    middle = trimmed[1:-1]
    while middle and total > MAX_PROMPT_CHARS:
        total -= _message_size(middle.pop(0))
    return [head, *middle, tail]


def _fill_required_defaults(schema: dict, arguments: dict) -> dict:
    """Supply required arguments the model left out, where a safe value exists.

    Models routinely omit required booleans and counters — sequentialthinking
    wants nextThoughtNeeded/thoughtNumber/totalThoughts and frequently sends
    only the thought. The server rejects the call, the round is wasted, and
    the user sees the model apologising to itself mid-answer.

    Only ever fills with the schema's own default or a falsy value of the
    declared type. That's deliberately conservative: an omitted flag becomes
    false rather than true, so nothing is enabled on the model's behalf, and a
    guess can't turn a read into a write.
    """
    properties = (schema or {}).get("properties") or {}
    required = list((schema or {}).get("required") or [])

    # Booleans are filled whether or not the schema calls them required,
    # because a server's own validator can be stricter than the schema it
    # publishes. sequentialthinking is exactly that: `required` omits
    # nextThoughtNeeded, and the server then rejects the call for missing it.
    # A flag the model didn't set is false either way, so supplying it changes
    # nothing except whether the call succeeds.
    required += [
        key
        for key, spec in properties.items()
        if (spec or {}).get("type") == "boolean" and key not in required
    ]

    filled = dict(arguments)
    for key in required:
        if key in filled and filled[key] is not None:
            continue
        spec = properties.get(key) or {}
        if "default" in spec:
            filled[key] = spec["default"]
            continue
        blank = {
            "boolean": False,
            "integer": 1,
            "number": 1,
            "string": "",
            "array": [],
            "object": {},
        }
        if spec.get("type") in blank:
            filled[key] = blank[spec["type"]]
    return filled


def _execute_tool(name: str, arguments: dict) -> str:
    info = _TOOL_INDEX.get(name)
    if info is None:
        _record_tool_use(name, ok=False, arguments=arguments, result=f"Error: unknown tool {name!r}")
        return f"Error: unknown tool {name!r}"
    if info.get("builtin"):
        try:
            result = _run_builtin_tool(
                name, _fill_required_defaults(info.get("input_schema") or {}, arguments)
            )
        except Exception as exc:  # noqa: BLE001 - report to the model, not a 500
            result = f"Error running tool {name!r}: {exc}"
        builtin_ok = not result.startswith("Error")
        _record_tool_use(name, ok=builtin_ok, arguments=arguments, result=result)
        if builtin_ok:
            _log_tool_call(name, arguments, result)
        return result
    call_args = _fill_required_defaults(info.get("input_schema") or {}, arguments)
    if info.get("api_key_param") and info.get("api_key"):
        call_args[info["api_key_param"]] = info["api_key"]
    try:
        result = asyncio.run(_async_call_tool(info["capability"], name, call_args))
        ok = True
    except Exception as exc:  # noqa: BLE001 - surface the failure to the model, not a 500
        result = f"Error calling tool {name!r}: {exc}"
        ok = False
    # Recorded and logged from here rather than from each provider's loop so
    # every path — chat, custom endpoints, cron — behaves identically. Failures
    # are logged too: knowing a call already failed is what stops the model
    # retrying it unchanged. The API key is deliberately taken from
    # `arguments`, not `call_args`, so an injected secret never lands on disk.
    _record_tool_use(name, ok=ok, arguments=arguments, result=result)
    _collect_attachments(result)
    # Only successes are persisted. A failure is still visible to the model
    # for the rest of THIS turn (it's in the conversation), which is what stops
    # a retry loop — but writing it to the durable log made a transient or
    # since-fixed failure permanent guidance, so an agent that hit a
    # permission error once would keep skipping that capability long after the
    # permission was granted.
    if ok:
        _log_tool_call(name, arguments, result)
    return result


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)

# Scaffolding some models write into `content` while also returning proper
# structured tool_calls — Hermes 4 emits a literal "<tool_call>" per call. It
# isn't prose and it isn't a tool call; it's protocol debris, and it became
# visible once interim narration started being kept.
_TOOL_SCAFFOLD = re.compile(
    r"</?\s*(tool_call|tool_response|function_call|function_results?)\s*>", re.IGNORECASE
)

# A whole XML tool-call block written as prose. Models fall back to this when
# they want another call but the loop has stopped offering tools — the answer
# then arrives as markup the user is left to interpret. Removed entirely
# rather than unwrapped: a call the runtime never executed has no result, so
# showing its arguments would only imply something happened.
_TOOL_CALL_BLOCK = re.compile(
    r"<\s*(function_calls|invoke|antml:invoke|parameter)\b[\s\S]*?(?:</\s*\1\s*>|$)",
    re.IGNORECASE,
)


def _strip_thinking(text: str) -> str:
    """Model output with its scaffolding removed.

    Some reasoning models (e.g. Groq's qwen/qwen3.6-27b) emit their chain of
    thought directly in `content` wrapped in <think> tags rather than in a
    separate `reasoning` field, and others leave tool-call markers behind.
    Neither belongs in a user-visible reply."""
    text = _THINK_BLOCK.sub("", text)
    text = _TOOL_CALL_BLOCK.sub("", text)
    text = _TOOL_SCAFFOLD.sub("", text)
    return text.strip()


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
        messages = [{"role": "system", "content": system_prompt}, *_trim_history(history)]
        # What the model says WHILE calling tools — "first find the components,
        # then solve for the time" — is the working, and it was being thrown away:
        # only the last message survived, so a decomposed answer arrived as a bare
        # "Final answer:" with the steps that justified it missing.
        narration: list[str] = []

        def _call_groq(use_tools: bool):
            kwargs = {"model": MODEL_ID, "max_tokens": 2048, "messages": _fit_to_budget(messages)}
            if use_tools and tools:
                kwargs["tools"] = tools
            return client.chat.completions.create(**kwargs)

        last_tool: str = ""
        for round_index in range(MAX_TOOL_ITERATIONS):
            # The status names the tool for the whole time it's in play —
            # while it runs and while the model reads what came back. Saying
            # "Thinking…" again in between makes the name flash past and
            # vanish, which reads as though the call was abandoned.
            _turn.round = round_index
            _set_status(f"Using {last_tool}…" if last_tool else "Thinking…")
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
                final = _strip_thinking(message.content or "")
                if narration and len(final) < STUB_REPLY_CHARS:
                    return "\n\n".join([*narration, final])
                return final

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
            # Keep the model's working, but not bare punctuation left behind
            # once scaffolding is stripped — that reads as a glitch, not a step.
            interim = _strip_thinking(message.content or "")
            if interim and any(ch.isalnum() for ch in interim):
                narration.append(interim)
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
                last_tool = _tool_label(tool_call.function.name)
                _set_status(f"Using {last_tool}…")
                result_text = _execute_tool(tool_call.function.name, arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": _clip(result_text, MAX_TOOL_RESULT_TO_MODEL),
                    }
                )

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
        messages = [{"role": "system", "content": system_prompt}, *_trim_history(history)]
        # What the model says WHILE calling tools — "first find the components,
        # then solve for the time" — is the working, and it was being thrown away:
        # only the last message survived, so a decomposed answer arrived as a bare
        # "Final answer:" with the steps that justified it missing.
        narration: list[str] = []

        last_tool: str = ""
        for round_index in range(MAX_TOOL_ITERATIONS):
            # The status names the tool for the whole time it's in play —
            # while it runs and while the model reads what came back. Saying
            # "Thinking…" again in between makes the name flash past and
            # vanish, which reads as though the call was abandoned.
            _turn.round = round_index
            _set_status(f"Using {last_tool}…" if last_tool else "Thinking…")
            kwargs = {"model": MODEL_ID, "max_tokens": 2048, "messages": _fit_to_budget(messages)}
            if tools:
                kwargs["tools"] = tools
            response = client.chat.completions.create(**kwargs)
            message = response.choices[0].message

            if not message.tool_calls:
                _set_status("Writing a reply…")
                final = _strip_thinking(message.content or "")
                if narration and len(final) < STUB_REPLY_CHARS:
                    return "\n\n".join([*narration, final])
                return final

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
            # Keep the model's working, but not bare punctuation left behind
            # once scaffolding is stripped — that reads as a glitch, not a step.
            interim = _strip_thinking(message.content or "")
            if interim and any(ch.isalnum() for ch in interim):
                narration.append(interim)
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
                last_tool = _tool_label(tool_call.function.name)
                _set_status(f"Using {last_tool}…")
                result_text = _execute_tool(tool_call.function.name, arguments)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": _clip(result_text, MAX_TOOL_RESULT_TO_MODEL),
                    }
                )

        _set_status("Writing the answer…")
        response = client.chat.completions.create(
            model=MODEL_ID, max_tokens=2048, messages=_fit_to_budget(messages)
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
    _begin_turn()
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
    return ChatResponse(reply=_with_attachments(reply), tools=[ToolUse(**t) for t in _turn_tools()])


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
