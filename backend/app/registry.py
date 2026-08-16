from app.schemas import CapabilityOption, EndpointTemplate, ModelOption

# Models that accept image input natively. Everything NOT listed here still
# supports images at the agent level — the agent runtime routes uploads
# through a vision sidecar and feeds the model a written description instead
# (see agent_runtime/app.py). So this set decides "real pixels vs. a
# description", not "images work vs. images don't".
#
# The Qwen VL entries are no longer offered as agent models (they don't do
# tool calling reliably, so they'd break MCP capabilities) — they're the
# sidecar's own models. They stay listed here so an agent created before that
# change still gets its image passed through natively instead of being
# needlessly round-tripped through a description of itself.
NATIVE_VISION_MODEL_IDS = {
    "Qwen/Qwen2.5-VL-72B-Instruct",
    "Qwen/Qwen2.5-VL-32B-Instruct",
    "Qwen/Qwen2.5-VL-7B-Instruct",
}

def supports_vision(model_provider: str, model_id: str) -> bool:
    """Whether this model can be handed a raw image, rather than needing the
    vision sidecar to describe it first."""
    return model_id in NATIVE_VISION_MODEL_IDS



# Capabilities the AGENT'S OWN container hosts, as stdio subprocesses, instead
# of reaching a shared capability container over the network.
#
# This is the difference that makes per-agent credentials possible at all: a
# shared container reads its key from its own environment once at startup, so
# every agent using it necessarily shares one token. A subprocess inside the
# agent's container gets that agent's environment, so each agent brings its
# own. It also gives each agent a private /scratch instead of one volume
# shared across every agent on the host, and removes a whole class of failure
# where one capability crash-looping takes an unrelated agent's tools down.
#
# `key_env` names the environment variable the server expects its credential
# in — the build pipeline resolves the agent's own key (or a platform key) and
# passes it through workspace.write_capabilities.
STDIO_SERVERS: dict[str, dict] = {
    "filesystem": {
        "command": "npx",
        # Scoped to /workspace/files: the server takes its allowed roots as
        # arguments, and handing it "/" would expose the agent's own source
        # and secrets. /workspace is the agent's bind-mounted volume, so this
        # persists across redeploys and is visible on the host, unlike the
        # container-local /scratch it used to point at.
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/workspace/files"],
    },
    "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "key_env": "GITHUB_PERSONAL_ACCESS_TOKEN",
    },
    "sequential_thinking": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sequential-thinking"],
    },
    "fetch": {
        "command": "python3",
        "args": ["-m", "mcp_server_fetch"],
    },
    "time": {
        "command": "python3",
        "args": ["-m", "mcp_server_time"],
    },
    "image_generation": {
        "command": "python3",
        "args": ["/app/image_server.py"],
    },
    "code_execution": {
        "command": "python3",
        "args": ["/app/code_server.py"],
    },
}

# Every Google capability is served by one process. It's handed the agent's
# REFRESH token, not an access token: access tokens last an hour and an agent
# is expected to outlive that, so the server re-exchanges as needed instead of
# the connection quietly dying mid-afternoon.
GOOGLE_STDIO_SERVER = {
    "command": "python3",
    "args": ["/app/google_server.py"],
}


# Which tools each Google capability owns. All of them are served by ONE
# process, so without this every tool gets labelled with whichever capability
# happened to be discovered last — a Classroom lookup showing up as
# "Calendar". Kept beside the scopes so the two stay in step.
GOOGLE_TOOLS: dict[str, list[str]] = {
    "calendar": ["list_calendar_events", "create_calendar_event"],
    "google_classroom": ["list_courses", "list_coursework"],
    "google_docs": ["create_doc", "read_doc", "append_doc"],
    "google_sheets": ["read_sheet", "append_sheet_row"],
    "google_drive": ["find_drive_files", "read_drive_file"],
}


def google_capabilities() -> list[str]:
    return [c.key for c in CAPABILITY_OPTIONS if c.oauth_provider == "google"]


def hosted_in_agent(capability_key: str) -> bool:
    """Whether this capability runs inside the agent's own container."""
    if capability_key in STDIO_SERVERS:
        return True
    capability = next((c for c in CAPABILITY_OPTIONS if c.key == capability_key), None)
    return bool(capability and capability.oauth_provider == "google")


MODEL_OPTIONS: list[ModelOption] = [
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        family="deepseek",
        family_label="DeepSeek",
        model_id="deepseek-ai/DeepSeek-V3.2",
        label="DeepSeek V3.2",
        description="DeepSeek's latest flagship — top-tier reasoning and tool use with a very large context window. Best free model for hard, multi-step agents.",
        available=True,
    ),
    # Every model here is served by Featherless and has been probed against
    # the live API to confirm it emits real, structured tool calls — that's
    # the bar for working MCP capabilities. Grouping is by who built the
    # weights (family), not by who serves them: "Llama"/"Qwen" is what people
    # actually shop by, and every entry would otherwise sit under one
    # undifferentiated "Featherless AI" heading.
    #
    # Fine-tunes are filed under the family they were trained from, per
    # Featherless's own model_class metadata — Hermes 4 70B is a Llama 3.1
    # 70B derivative, Hermes 4 14B a Qwen 3 14B one.

    # --- Llama ---
    # Hermes leads the family on purpose: the wizard defaults to the first
    # available model in this list, and Meta's own `meta-llama/*` builds are
    # frequently capacity-exhausted on Featherless, so defaulting to one of
    # those hands a new user a deploy failure through no fault of their own.
    # Hermes 4 is the same Llama 3.1 70B weights served from a pool that has
    # answered every time it's been polled.
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        family="llama",
        family_label="Llama",
        model_id="NousResearch/Hermes-4-70B",
        label="Hermes 4 70B",
        description="Nous Research's tool-use-tuned Llama 3.1 70B. Note: it is a reasoning model that writes its thinking out as ordinary reply text rather than in a separate field, so replies can arrive as visible deliberation and get cut off mid-thought. Prefer DeepSeek or Qwen unless you specifically want that.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        family="llama",
        family_label="Llama",
        model_id="meta-llama/Llama-3.1-8B-Instruct",
        label="Llama 3.1 8B Instruct",
        description="Fast and lightweight Llama model. Good for simple agents where speed matters. Note: Meta's own Llama builds are often at capacity on Featherless — if a deploy fails with a capacity error, try Hermes 4 instead.",
        available=True,
    ),

    # --- DeepSeek ---
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        family="deepseek",
        family_label="DeepSeek",
        model_id="deepseek-ai/DeepSeek-V3.1-Terminus",
        label="DeepSeek V3.1 Terminus",
        description="Stable, heavily-tested DeepSeek release — excellent reasoning and reliable tool calling.",
        available=True,
    ),

    # --- Mistral ---
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        family="mistral",
        family_label="Mistral",
        model_id="mistralai/Mistral-Large-Instruct-2411",
        label="Mistral Large",
        description="Mistral's flagship open model — strong general reasoning with dependable function calling.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        family="mistral",
        family_label="Mistral",
        model_id="mistralai/Mistral-Medium-3.5-128B",
        label="Mistral Medium 3.5",
        description="Mid-size Mistral with a 128K context window — good for agents that need to hold a lot of material at once.",
        available=True,
    ),

    # --- Qwen ---
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        family="qwen",
        family_label="Qwen",
        model_id="Qwen/Qwen3-Coder-480B-A35B-Instruct",
        label="Qwen 3 Coder 480B",
        description="Qwen's largest agentic coding model — the strongest tool user in the catalog. Best for agents that chain many capability calls.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        family="qwen",
        family_label="Qwen",
        model_id="Qwen/Qwen3-Coder-30B-A3B-Instruct",
        label="Qwen 3 Coder 30B",
        description="Mixture-of-experts coding model — strong tool use at a fraction of the 480B's cost and latency.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        family="qwen",
        family_label="Qwen",
        model_id="Qwen/Qwen2.5-72B-Instruct",
        label="Qwen 2.5 72B",
        description="Most capable general-purpose Qwen — strong reasoning, coding, and tool use. Supports all MCP capabilities.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        family="qwen",
        family_label="Qwen",
        model_id="Qwen/Qwen2.5-32B-Instruct",
        label="Qwen 2.5 32B",
        description="Large model with strong tool use and reasoning. Good balance of capability and speed.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        family="qwen",
        family_label="Qwen",
        model_id="Qwen/Qwen2.5-14B-Instruct",
        label="Qwen 2.5 14B",
        description="Mid-size model — fast responses with reliable tool use. Good for most agents.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        family="qwen",
        family_label="Qwen",
        model_id="Qwen/Qwen2.5-7B-Instruct",
        label="Qwen 2.5 7B",
        description="Fast lightweight model that still supports tool calling. Best for simple agents.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        family="qwen",
        family_label="Qwen",
        model_id="Qwen/Qwen3-4B-Instruct-2507",
        label="Qwen 3 4B",
        description="Very fast small model that still emits proper tool calls. Best when latency matters more than depth.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        family="qwen",
        family_label="Qwen",
        model_id="NousResearch/Hermes-4-14B",
        label="Hermes 4 14B",
        description="Nous Research's agentic tune of Qwen 3 14B — tool-use focused, with faster and cheaper responses than the 70B.",
        available=True,
    ),
]

CAPABILITY_OPTIONS: list[CapabilityOption] = [
    # --- Wired: run as real MCP servers in their own containers ---
    CapabilityOption(
        key="wolfram_alpha",
        name="WolframAlpha",
        description="Answer computational, math, science, and factual queries via Wolfram|Alpha.",
        icon="🧮",
        wired=True,
        mcp_server="wolfram_alpha",
        requires_api_key=True,
        api_key_help=(
            "Free — sign up at developer.wolframalpha.com/access, create an app, and copy its AppID."
        ),
    ),
    CapabilityOption(
        key="firecrawl",
        name="Web Search & Scrape",
        description="Search the web and scrape any webpage into clean markdown. Powered by Firecrawl — handles JavaScript-heavy sites, extracts structured data, and crawls entire sites.",
        icon="🔍",
        wired=True,
        mcp_server="firecrawl",
    ),
    # NOTE: "Image Recognition" used to be listed here. It's no longer a
    # capability you attach — every agent can be shown an image, because the
    # runtime routes uploads through a vision sidecar when the agent's own
    # model can't read them. Leaving it in the picker implied agents without it
    # couldn't see, which stopped being true and only produced agents with the
    # attach button mysteriously missing.
    CapabilityOption(
        key="desmos",
        name="Desmos Graphing",
        description=(
            "Plot equations on an interactive Desmos graph the user can zoom, pan and trace, or "
            "render one as an image the agent can attach to its reply — far more useful than "
            "describing a curve in words."
        ),
        icon="📈",
        wired=True,
        mcp_server="desmos",
    ),
    CapabilityOption(
        key="code_execution",
        name="Code Execution",
        description=(
            "Run Python and shell commands in this agent's own workspace and read the output. "
            "Lets an agent test what it writes and fix it from the traceback, instead of "
            "handing over code nobody has run. Runs inside this agent's container."
        ),
        icon="⚙️",
        wired=True,
        mcp_server="code_execution",
    ),
    CapabilityOption(
        key="time",
        name="Time",
        description="Get the current time in any timezone, or convert a time between timezones.",
        icon="🕒",
        wired=True,
        mcp_server="time",
    ),
    CapabilityOption(
        key="sequential_thinking",
        name="Sequential Thinking",
        description="A structured scratchpad the agent can use to reason step-by-step through a complex problem before answering.",
        icon="🧠",
        wired=True,
        mcp_server="sequential_thinking",
    ),
    CapabilityOption(
        key="filesystem",
        name="Filesystem",
        description=(
            "Read and write files in a folder that belongs to this agent alone. Files persist "
            "across redeploys and are visible on the host, so an agent can build up a project "
            "over several sessions. Capped at 2 GB."
        ),
        icon="🗂️",
        wired=True,
        mcp_server="filesystem",
    ),
    # --- Stubbed: recorded on the agent, not yet executable ---
    CapabilityOption(
        key="google_places",
        name="Google Places",
        description="Search restaurants/locations and return coordinates.",
        icon="📍",
        wired=False,
    ),
    CapabilityOption(
        key="duffel_stays",
        name="Duffel Stays",
        description="Search and book hotel rooms (sandbox mode).",
        icon="🏨",
        wired=False,
    ),
    CapabilityOption(
        key="restaurant_reservation",
        name="Restaurant Reservation",
        description="Book a real table via guest checkout (no stored credentials).",
        icon="🍽️",
        wired=False,
    ),
    CapabilityOption(
        key="calendar",
        name="Calendar",
        description="Check and hold dates on a calendar.",
        icon="📅",
        wired=True,
        mcp_server="google",
        oauth_provider="google",
        oauth_scopes=['https://www.googleapis.com/auth/calendar.events'],
    ),
    CapabilityOption(
        key="slack",
        name="Slack",
        description="Send messages and read channels in a Slack workspace.",
        icon="💬",
        wired=False,
    ),
    CapabilityOption(
        key="gmail",
        name="Gmail",
        description="Read, draft, and send email through Gmail.",
        icon="📧",
        wired=False,
        oauth_provider="google",
        oauth_scopes=['https://www.googleapis.com/auth/gmail.modify'],
    ),
    CapabilityOption(
        key="google_sheets",
        name="Google Sheets",
        description="Read and write rows in a Google Sheet.",
        icon="📊",
        wired=True,
        mcp_server="google",
        oauth_provider="google",
        oauth_scopes=["https://www.googleapis.com/auth/spreadsheets"],
    ),
    CapabilityOption(
        key="google_docs",
        name="Google Docs",
        description="Read, draft and edit Google Docs.",
        icon="📝",
        wired=True,
        mcp_server="google",
        oauth_provider="google",
        oauth_scopes=["https://www.googleapis.com/auth/documents"],
    ),
    CapabilityOption(
        key="google_slides",
        name="Google Slides",
        description="Build and edit slide decks in Google Slides.",
        icon="🖼️",
        wired=False,
        oauth_provider="google",
        oauth_scopes=["https://www.googleapis.com/auth/presentations"],
    ),
    CapabilityOption(
        key="google_drive",
        name="Google Drive",
        description="Find, open and save files in Google Drive.",
        icon="📁",
        wired=True,
        mcp_server="google",
        oauth_provider="google",
        # drive.file covers only files the agent itself created, so Drive
        # answers 404 — not 403 — for anything else, including a teacher's
        # Classroom attachment. Reading files the user already has requires
        # drive.readonly, which is one of Google's RESTRICTED scopes: fine
        # while the app is in Testing, but publishing it needs an annual
        # third-party security assessment. Both are requested so an agent can
        # write its own files and read the user's.
        oauth_scopes=[
            "https://www.googleapis.com/auth/drive.file",
            "https://www.googleapis.com/auth/drive.readonly",
        ],
    ),
    CapabilityOption(
        key="google_classroom",
        name="Google Classroom",
        description="Look up courses, assignments and due dates in Google Classroom.",
        icon="🎓",
        wired=True,
        mcp_server="google",
        oauth_provider="google",
        # Read-only, and deliberately no roster scope: student rosters are
        # restricted, and reading other people's coursework raises a consent
        # question a demo shouldn't quietly answer for its users.
        #
        # BOTH coursework scopes, because which one applies depends on the
        # user's role in the course, not on what the agent is asked to do.
        # `coursework.me` covers work assigned to you as a STUDENT; a teacher
        # listing assignments in a course they own needs
        # `coursework.students`. Requesting only the first makes the agent
        # work for students and 403 for teachers — with an error that names
        # permission rather than role, so it reads like a bug.
        oauth_scopes=[
            "https://www.googleapis.com/auth/classroom.courses.readonly",
            "https://www.googleapis.com/auth/classroom.coursework.me.readonly",
            "https://www.googleapis.com/auth/classroom.coursework.students.readonly",
        ],
    ),
    CapabilityOption(
        key="notion",
        name="Notion",
        description="Create and update pages or databases in Notion.",
        icon="📝",
        wired=False,
    ),
    CapabilityOption(
        key="github",
        name="GitHub",
        description=(
            "Open issues, read PRs, search code, and manage repos via the GitHub API. Uses a "
            "single platform-configured token shared by every agent (not a per-agent key — this "
            "wraps the official reference server, which only reads its token from the container's "
            "own environment at startup)."
        ),
        icon="🐙",
        wired=True,
        mcp_server="github",
    ),
    CapabilityOption(
        key="stripe",
        name="Stripe",
        description="Look up charges and customers, or issue refunds.",
        icon="💳",
        wired=False,
    ),
    CapabilityOption(
        key="twilio",
        name="Twilio",
        description="Send SMS messages or make calls.",
        icon="📱",
        wired=False,
    ),
    CapabilityOption(
        key="weather",
        name="Weather",
        description="Get current conditions and forecasts for a location.",
        icon="⛅",
        wired=False,
    ),
    CapabilityOption(
        key="spotify",
        name="Spotify",
        description="Search tracks and control playback on Spotify.",
        icon="🎵",
        wired=False,
    ),
    CapabilityOption(
        key="linear",
        name="Linear",
        description="Create and triage issues in a Linear project.",
        icon="📋",
        wired=False,
    ),
    CapabilityOption(
        key="jira",
        name="Jira",
        description="Create and update tickets in a Jira project.",
        icon="🗂️",
        wired=False,
    ),
    # NOTE: a separate "Web Search" capability backed by Brave used to sit
    # here. Firecrawl already searches AND scrapes, so Brave was a second way
    # to do the same job that additionally demanded its own key — two entries
    # for one capability is a choice users shouldn't have to make.
    CapabilityOption(
        key="image_generation",
        name="Image Generation",
        description="Generate images from a text description — diagrams, illustrations, mock-ups. No API key needed.",
        icon="🎨",
        wired=True,
        mcp_server="image_generation",
    ),
    CapabilityOption(
        key="discord",
        name="Discord",
        description="Send messages and manage channels in a Discord server.",
        icon="🎮",
        wired=False,
    ),
    CapabilityOption(
        key="hubspot",
        name="HubSpot",
        description="Look up and update contacts or deals in HubSpot CRM.",
        icon="🧲",
        wired=False,
    ),
    CapabilityOption(
        key="zapier",
        name="Zapier",
        description="Trigger a Zapier workflow from this agent.",
        icon="⚡",
        wired=False,
    ),
    CapabilityOption(
        key="airtable",
        name="Airtable",
        description="Read and write records in an Airtable base.",
        icon="🗃️",
        wired=False,
    ),
    CapabilityOption(
        key="salesforce",
        name="Salesforce",
        description="Look up and update Salesforce records.",
        icon="☁️",
        wired=False,
    ),
]


# Ready-made endpoints, so an API-integrating agent doesn't start from a blank
# form. Each one is a whole EndpointSpec minus its id — the picker adds that.
#
# The instructions are written the way the runtime consumes them: it appends
# `Input (JSON): {...}` and "Respond with just the result", so each instruction
# refers to input fields by name and states the output shape exactly. Anything
# vaguer produces a preamble the caller then has to strip.
ENDPOINT_TEMPLATES: list[EndpointTemplate] = [
    EndpointTemplate(
        key="summarize",
        name="Summarize",
        icon="📝",
        summary="Condense any text to a length you choose.",
        path="/summarize",
        description="Summarize a block of text.",
        # `length` is an enum of sentence counts rather than a max_words
        # integer on purpose. A word budget reads better in an API, but these
        # models don't reliably count words — a 25-word ceiling came back at
        # 41 no matter how forcefully the instruction was worded. Sentence
        # counts they do honour, so the knob is one the agent can actually
        # keep.
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "length": {
                    "type": "string",
                    "enum": ["one_line", "short", "detailed"],
                    "default": "short",
                },
            },
            "required": ["text"],
        },
        instruction=(
            "Summarize the text in the input at the length given by `length`, defaulting to "
            "short: `one_line` is exactly one sentence, `short` is at most three sentences, "
            "`detailed` is at most eight. Preserve names, numbers, dates, and any decision or "
            "action the text records — where it won't all fit, drop the least consequential "
            "detail rather than running past the sentence limit. Write plain prose: no bullet "
            "points, no heading, and don't open with \"This text is about\"."
        ),
    ),
    EndpointTemplate(
        key="ask",
        name="Ask a question",
        icon="❓",
        summary="Answer a question, optionally only from context you pass in.",
        path="/ask",
        description="Answer a question, optionally against supplied context.",
        input_schema={
            "type": "object",
            "properties": {"question": {"type": "string"}, "context": {"type": "string"}},
            "required": ["question"],
        },
        instruction=(
            "Answer the question. If `context` is present, answer only from it — and when it "
            "doesn't contain the answer, say so plainly rather than filling the gap from general "
            "knowledge. If `context` is absent, answer from what you know and from any tools you "
            "have."
        ),
    ),
    EndpointTemplate(
        key="extract",
        name="Extract fields",
        icon="🧾",
        summary="Pull named fields out of messy text as JSON.",
        path="/extract",
        description="Extract named fields from unstructured text.",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "fields": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["text", "fields"],
        },
        instruction=(
            "Extract each of the named `fields` from `text`. Respond with a single JSON object "
            "whose keys are exactly the requested field names and nothing else — no code fence, no "
            "commentary. Use null for any field the text doesn't contain; never guess a value."
        ),
    ),
    EndpointTemplate(
        key="classify",
        name="Classify",
        icon="🏷️",
        summary="Sort text into one of your own categories.",
        path="/classify",
        description="Assign text to one of a caller-supplied set of categories.",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "categories": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["text", "categories"],
        },
        instruction=(
            "Choose the single category from `categories` that best fits `text`. Respond with that "
            "category written exactly as it appeared in the input, and nothing else. If none of "
            "them fit, respond with `none`."
        ),
    ),
    EndpointTemplate(
        key="translate",
        name="Translate",
        icon="🌐",
        summary="Translate text into another language, formatting intact.",
        path="/translate",
        description="Translate text into a target language.",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}, "target_language": {"type": "string"}},
            "required": ["text", "target_language"],
        },
        instruction=(
            "Translate `text` into `target_language`. Return only the translation — no "
            "transliteration, no translator's notes, no copy of the original. Keep line breaks, "
            "names and numbers intact, and leave code and URLs untranslated."
        ),
    ),
    EndpointTemplate(
        key="draft_reply",
        name="Draft a reply",
        icon="✉️",
        summary="Write a reply to a message in the tone you pick.",
        path="/draft-reply",
        description="Draft a reply to an incoming message.",
        input_schema={
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "tone": {"type": "string", "default": "friendly and professional"},
                "notes": {"type": "string"},
            },
            "required": ["message"],
        },
        instruction=(
            "Draft a reply to `message`. Match the tone named in `tone`, defaulting to friendly "
            "and professional, and cover every point in `notes` if it is present. Return only the "
            "body of the reply — no subject line, no \"here's a draft\", and no bracketed "
            "placeholder for a name the input never gave you."
        ),
    ),
    EndpointTemplate(
        key="grade",
        name="Grade an answer",
        icon="🎓",
        summary="Mark a student's answer against a rubric, with feedback.",
        path="/grade",
        description="Score a student answer and explain the mark.",
        input_schema={
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "student_answer": {"type": "string"},
                "rubric": {"type": "string"},
                "max_points": {"type": "number", "default": 10},
            },
            "required": ["question", "student_answer"],
        },
        instruction=(
            "Mark `student_answer` against `question`, applying `rubric` if one is given. Work the "
            "problem out yourself first, then compare — do not award credit to a confident wrong "
            "answer. Respond in exactly this shape: a first line reading `Score: X/Y` out of "
            "`max_points` (10 if absent), then a short paragraph on what earned credit and what "
            "didn't, then — only when the answer is wrong — the specific step where it went wrong. "
            "Check your own solution before you mark against it; a mistake here costs the student "
            "marks they earned."
        ),
        suggested_capability="wolfram_alpha",
    ),
    EndpointTemplate(
        key="solve",
        name="Solve a problem",
        icon="🧮",
        summary="Work a maths or science problem step by step.",
        path="/solve",
        description="Solve a maths or science problem, showing the working.",
        input_schema={
            "type": "object",
            "properties": {
                "problem": {"type": "string"},
                "show_work": {"type": "boolean", "default": True},
            },
            "required": ["problem"],
        },
        instruction=(
            "Solve `problem`. Break it into sub-problems and check each numeric or symbolic step "
            "with a tool where you have one rather than doing the arithmetic in your head. When "
            "`show_work` is true or absent, show the steps in order and put the final answer on a "
            "line of its own at the end; when it is false, give only the final answer. Before you "
            "state that final answer, re-read your own working and confirm the answer you are "
            "about to write is the one you actually derived — a correct derivation written up "
            "backwards is still a wrong answer."
        ),
        suggested_capability="wolfram_alpha",
    ),
    EndpointTemplate(
        key="research",
        name="Research brief",
        icon="🔍",
        summary="Research a topic on the live web and return a sourced brief.",
        path="/research",
        description="Research a topic on the web and return a brief with sources.",
        input_schema={
            "type": "object",
            "properties": {
                "topic": {"type": "string"},
                "max_sources": {"type": "integer", "default": 5},
            },
            "required": ["topic"],
        },
        instruction=(
            "Research `topic` on the live web and write a brief. Search first — do not answer from "
            "memory. Use at most `max_sources` sources, or 5 if that field is absent. Structure it "
            "as a two-sentence summary, then the key findings as short bullets, then a `Sources:` "
            "list of the URLs you actually opened. Say so plainly where the sources disagree or "
            "where you could not verify something."
        ),
        suggested_capability="firecrawl",
    ),
]

# A template pointing at a capability key that no longer exists would render a
# hint for a capability the user can't attach, so catch the rename here rather
# than in the picker.
_CAPABILITY_KEYS = {c.key for c in CAPABILITY_OPTIONS}
for _template in ENDPOINT_TEMPLATES:
    if _template.suggested_capability and _template.suggested_capability not in _CAPABILITY_KEYS:
        raise RuntimeError(
            f"Endpoint template {_template.key!r} suggests unknown capability "
            f"{_template.suggested_capability!r}"
        )
