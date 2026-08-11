from app.schemas import CapabilityOption, ModelOption

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
        # Scoped to /scratch: the server takes its allowed roots as arguments,
        # and handing it "/" would expose the agent's own source and secrets.
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "/scratch"],
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
    "desmos": {
        "command": "python3",
        "args": ["/app/desmos_server.py"],
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
    "google_docs": ["create_doc", "read_doc"],
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
        description="Nous Research's tool-use-tuned Llama 3.1 70B — built specifically for agentic workflows and structured output.",
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
        model_id="deepseek-ai/DeepSeek-V3.2",
        label="DeepSeek V3.2",
        description="DeepSeek's latest flagship — top-tier reasoning and tool use with a very large context window. Best free model for hard, multi-step agents.",
        available=True,
    ),
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
            "Plot equations on an interactive Desmos graph the user can zoom, pan and trace — "
            "far more useful than describing a curve in words."
        ),
        icon="📈",
        wired=True,
        mcp_server="desmos",
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
            "Read and write files in a scratch directory. Note: this is a shared scratch space "
            "across every agent using this capability, not private per-agent storage."
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
