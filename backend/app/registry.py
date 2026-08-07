from app.schemas import CapabilityOption, ModelOption

MODEL_OPTIONS: list[ModelOption] = [
    # --- Anthropic — wired, needs ANTHROPIC_API_KEY ---
    ModelOption(
        provider="anthropic",
        provider_label="Anthropic",
        model_id="claude-sonnet-5",
        label="Claude Sonnet 5",
        description="Anthropic's balanced flagship — strong reasoning and tool use at moderate cost. A safe default for most agents.",
        available=True,
    ),
    ModelOption(
        provider="anthropic",
        provider_label="Anthropic",
        model_id="claude-opus-5",
        label="Claude Opus 5",
        description="Anthropic's most capable model. Best for agents that need to reason through complex, multi-step tasks.",
        available=True,
    ),
    ModelOption(
        provider="anthropic",
        provider_label="Anthropic",
        model_id="claude-haiku-4-5-20251001",
        label="Claude Haiku 4.5",
        description="Anthropic's fastest, cheapest model. Good for simple, high-volume agents where latency matters most.",
        available=True,
    ),
    # --- Groq — wired, needs GROQ_API_KEY. All of these are real models
    # confirmed live on Groq's API (not aspirational) as of this build. ---
    ModelOption(
        provider="groq",
        provider_label="Groq",
        model_id="llama-3.3-70b-versatile",
        label="Llama 3.3 70B Versatile",
        description="Open-weight Llama 3.3, served on Groq's low-latency hardware. Solid general-purpose reasoning.",
        available=True,
    ),
    ModelOption(
        provider="groq",
        provider_label="Groq",
        model_id="llama-3.1-8b-instant",
        label="Llama 3.1 8B Instant",
        description="A small, very fast Llama model on Groq. Best for simple agents where speed matters more than depth.",
        available=True,
    ),
    ModelOption(
        provider="groq",
        provider_label="Groq",
        model_id="openai/gpt-oss-120b",
        label="GPT-OSS 120B",
        description="OpenAI's open-weight model, served on Groq. Large, strong general reasoning.",
        available=True,
    ),
    ModelOption(
        provider="groq",
        provider_label="Groq",
        model_id="openai/gpt-oss-20b",
        label="GPT-OSS 20B",
        description="OpenAI's open-weight model, smaller size, served on Groq for faster/cheaper responses.",
        available=True,
    ),
    ModelOption(
        provider="groq",
        provider_label="Groq",
        model_id="qwen/qwen3.6-27b",
        label="Qwen 3.6 27B",
        description="Alibaba's open-weight Qwen model, served on Groq. Strong multilingual and coding ability.",
        available=True,
    ),
    ModelOption(
        provider="groq",
        provider_label="Groq",
        model_id="groq/compound",
        label="Groq Compound",
        description="Groq's own agentic system model with built-in web search and code execution.",
        available=True,
    ),
    ModelOption(
        provider="groq",
        provider_label="Groq",
        model_id="groq/compound-mini",
        label="Groq Compound Mini",
        description="A smaller, faster version of Groq Compound.",
        available=True,
    ),
    # --- OpenAI — direct API, not wired up yet ---
    ModelOption(
        provider="openai",
        provider_label="OpenAI",
        model_id="gpt-5",
        label="GPT-5 — coming soon",
        description="OpenAI's flagship model. Direct OpenAI API integration isn't wired up yet.",
        available=False,
    ),
    ModelOption(
        provider="openai",
        provider_label="OpenAI",
        model_id="gpt-5-mini",
        label="GPT-5 Mini — coming soon",
        description="A smaller, faster GPT-5 variant. Direct OpenAI API integration isn't wired up yet.",
        available=False,
    ),
    ModelOption(
        provider="openai",
        provider_label="OpenAI",
        model_id="o3",
        label="o3 — coming soon",
        description="OpenAI's reasoning-focused model. Direct OpenAI API integration isn't wired up yet.",
        available=False,
    ),
    # --- Moonshot AI (Kimi) — not wired up yet ---
    ModelOption(
        provider="moonshot",
        provider_label="Moonshot AI (Kimi)",
        model_id="kimi-k2",
        label="Kimi K2 — coming soon",
        description="Moonshot AI's flagship open-weight model, strong at agentic tool use. Not wired up yet.",
        available=False,
    ),
    ModelOption(
        provider="moonshot",
        provider_label="Moonshot AI (Kimi)",
        model_id="kimi-k1.5",
        label="Kimi K1.5 — coming soon",
        description="Moonshot AI's multimodal reasoning model. Not wired up yet.",
        available=False,
    ),
    # --- Meta (Llama) — open-weight; run via Groq above, or locally via
    # Ollama below. Listed here as its own family for browsing. ---
    ModelOption(
        provider="meta",
        provider_label="Meta (Llama)",
        model_id="llama-4-maverick",
        label="Llama 4 Maverick — coming soon",
        description="Meta's large open-weight model. Served via a provider like Groq, or run locally — direct hosting not wired up yet.",
        available=False,
    ),
    ModelOption(
        provider="meta",
        provider_label="Meta (Llama)",
        model_id="llama-4-scout",
        label="Llama 4 Scout — coming soon",
        description="Meta's efficient open-weight model with a long context window. Not wired up yet.",
        available=False,
    ),
    ModelOption(
        provider="meta",
        provider_label="Meta (Llama)",
        model_id="llama-3.1-405b",
        label="Llama 3.1 405B — coming soon",
        description="Meta's largest Llama 3 model. Not wired up yet.",
        available=False,
    ),
    # --- Google (Gemini) — not wired up yet ---
    ModelOption(
        provider="google",
        provider_label="Google (Gemini)",
        model_id="gemini-2.5-pro",
        label="Gemini 2.5 Pro — coming soon",
        description="Google's flagship multimodal model. Not wired up yet.",
        available=False,
    ),
    ModelOption(
        provider="google",
        provider_label="Google (Gemini)",
        model_id="gemini-2.5-flash",
        label="Gemini 2.5 Flash — coming soon",
        description="Google's fast, low-cost multimodal model. Not wired up yet.",
        available=False,
    ),
    # --- Mistral AI — not wired up yet ---
    ModelOption(
        provider="mistral",
        provider_label="Mistral AI",
        model_id="mistral-large",
        label="Mistral Large — coming soon",
        description="Mistral's flagship model. Not wired up yet.",
        available=False,
    ),
    ModelOption(
        provider="mistral",
        provider_label="Mistral AI",
        model_id="mistral-small",
        label="Mistral Small — coming soon",
        description="Mistral's fast, low-cost model. Not wired up yet.",
        available=False,
    ),
    # --- DeepSeek — not wired up yet ---
    ModelOption(
        provider="deepseek",
        provider_label="DeepSeek",
        model_id="deepseek-v3",
        label="DeepSeek V3 — coming soon",
        description="DeepSeek's general-purpose open-weight model. Not wired up yet.",
        available=False,
    ),
    ModelOption(
        provider="deepseek",
        provider_label="DeepSeek",
        model_id="deepseek-r1",
        label="DeepSeek R1 — coming soon",
        description="DeepSeek's reasoning-focused model. Not wired up yet.",
        available=False,
    ),
    # --- xAI (Grok) — not wired up yet ---
    ModelOption(
        provider="xai",
        provider_label="xAI (Grok)",
        model_id="grok-4",
        label="Grok 4 — coming soon",
        description="xAI's flagship model. Not wired up yet.",
        available=False,
    ),
    ModelOption(
        provider="xai",
        provider_label="xAI (Grok)",
        model_id="grok-3-mini",
        label="Grok 3 Mini — coming soon",
        description="xAI's fast, low-cost model. Not wired up yet.",
        available=False,
    ),
    # --- Ollama (Local) — runs on your own hardware, no API key or network
    # call required. Hosting mode is a disabled stub until this is wired up. ---
    ModelOption(
        provider="ollama",
        provider_label="Ollama (Local)",
        model_id="llama3.3",
        label="Llama 3.3 — coming soon",
        description="Run Meta's Llama 3.3 entirely on your own hardware, no external API calls. Not wired up yet.",
        available=False,
    ),
    ModelOption(
        provider="ollama",
        provider_label="Ollama (Local)",
        model_id="qwen2.5:3b",
        label="Qwen 2.5 (3B)",
        description=(
            "Runs entirely on this machine via a shared Ollama container — no API key, no data "
            "leaves your machine. Smaller and less capable than the hosted models, and doesn't "
            "support tool use (capabilities) yet. First deploy pulls a ~2GB model file."
        ),
        available=True,
    ),
    ModelOption(
        provider="ollama",
        provider_label="Ollama (Local)",
        model_id="llava",
        label="LLaVA (vision, 7B)",
        description=(
            "A local vision-capable model — runs entirely on this machine, no API key. Supports "
            "the Image Recognition capability. First deploy pulls a ~4.7GB model file."
        ),
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
        key="browser_use",
        name="Browser Use",
        description="Browse and interact with real webpages headlessly via Playwright — for sites without a clean API.",
        icon="🌐",
        wired=True,
        mcp_server="playwright",
    ),
    CapabilityOption(
        key="image_recognition",
        name="Image Recognition",
        description="Lets the agent see and analyze images you upload in chat. Requires a vision-capable model — any Anthropic (Claude) model, or the local LLaVA model. Groq models don't support image input.",
        icon="🖼️",
        wired=True,
        mcp_server=None,
    ),
    CapabilityOption(
        key="fetch",
        name="Fetch",
        description="Fetch a real webpage and read its content, converted to clean text/markdown.",
        icon="📄",
        wired=True,
        mcp_server="fetch",
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
        wired=False,
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
    ),
    CapabilityOption(
        key="google_sheets",
        name="Google Sheets",
        description="Read and write rows in a Google Sheet.",
        icon="📊",
        wired=False,
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
    CapabilityOption(
        key="web_search",
        name="Web Search",
        description=(
            "Run live web searches via Brave Search and return summarized results. Uses a single "
            "platform-configured key shared by every agent (not a per-agent key — see GitHub's "
            "note above for why)."
        ),
        icon="🔍",
        wired=True,
        mcp_server="brave_search",
    ),
    CapabilityOption(
        key="image_generation",
        name="Image Generation",
        description="Generate images from a text prompt.",
        icon="🎨",
        wired=False,
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
