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

# Providers whose whole current lineup takes image input, so individual model
# IDs don't have to be enumerated.
NATIVE_VISION_PROVIDERS = {"anthropic"}


def supports_vision(model_provider: str, model_id: str) -> bool:
    """Whether this model can be handed a raw image, rather than needing the
    vision sidecar to describe it first."""
    return model_provider in NATIVE_VISION_PROVIDERS or model_id in NATIVE_VISION_MODEL_IDS


MODEL_OPTIONS: list[ModelOption] = [
    # --- Anthropic — requires paid API key ---
    ModelOption(
        provider="anthropic",
        provider_label="Anthropic",
        model_id="claude-sonnet-5",
        label="Claude Sonnet 5",
        description="Anthropic's balanced flagship — strong reasoning and tool use at moderate cost. Requires your own API key.",
        available=False,
    ),
    ModelOption(
        provider="anthropic",
        provider_label="Anthropic",
        model_id="claude-opus-5",
        label="Claude Opus 5",
        description="Anthropic's most capable model. Best for agents that need to reason through complex, multi-step tasks. Requires your own API key.",
        available=False,
    ),
    ModelOption(
        provider="anthropic",
        provider_label="Anthropic",
        model_id="claude-haiku-4-5-20251001",
        label="Claude Haiku 4.5",
        description="Anthropic's fastest, cheapest model. Good for simple, high-volume agents where latency matters most. Requires your own API key.",
        available=False,
    ),
    # --- Groq — requires paid API key ---
    ModelOption(
        provider="groq",
        provider_label="Groq",
        model_id="llama-3.3-70b-versatile",
        label="Llama 3.3 70B Versatile",
        description="Open-weight Llama 3.3, served on Groq's low-latency hardware. Requires your own API key.",
        available=False,
    ),
    ModelOption(
        provider="groq",
        provider_label="Groq",
        model_id="llama-3.1-8b-instant",
        label="Llama 3.1 8B Instant",
        description="A small, very fast Llama model on Groq. Requires your own API key.",
        available=False,
    ),
    ModelOption(
        provider="groq",
        provider_label="Groq",
        model_id="openai/gpt-oss-120b",
        label="GPT-OSS 120B",
        description="OpenAI's open-weight model, served on Groq. Requires your own API key.",
        available=False,
    ),
    ModelOption(
        provider="groq",
        provider_label="Groq",
        model_id="openai/gpt-oss-20b",
        label="GPT-OSS 20B",
        description="OpenAI's open-weight model, smaller size, served on Groq. Requires your own API key.",
        available=False,
    ),
    ModelOption(
        provider="groq",
        provider_label="Groq",
        model_id="qwen/qwen3.6-27b",
        label="Qwen 3.6 27B",
        description="Alibaba's open-weight Qwen model, served on Groq. Requires your own API key.",
        available=False,
    ),
    ModelOption(
        provider="groq",
        provider_label="Groq",
        model_id="groq/compound",
        label="Groq Compound",
        description="Groq's own agentic system model with built-in web search and code execution. Requires your own API key.",
        available=False,
    ),
    ModelOption(
        provider="groq",
        provider_label="Groq",
        model_id="groq/compound-mini",
        label="Groq Compound Mini",
        description="A smaller, faster version of Groq Compound. Requires your own API key.",
        available=False,
    ),
    # --- Featherless AI — every model below emitted a real, structured
    # tool_call when probed against the live API, which is what MCP
    # capabilities require. Models that only *describe* a tool call in prose
    # (Qwen2.5-Coder-32B, Mistral-Small-3.2, Magistral-Small, Devstral-Small),
    # that return malformed tool arguments (Hermes-3-70B emits concatenated
    # JSON objects), or that aren't reachable on this plan at all
    # (Llama-3.3-70B is gated) are deliberately left out: with those, an agent
    # would look like it had capabilities and then silently never use them. ---
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="meta-llama/Llama-3.1-70B-Instruct",
        label="Llama 3.1 70B Instruct",
        description="Meta's flagship open model — strong reasoning, coding, and tool use support.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="meta-llama/Llama-3.1-8B-Instruct",
        label="Llama 3.1 8B Instruct",
        description="Fast and lightweight Llama model. Good for simple agents where speed matters.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="Qwen/Qwen2.5-72B-Instruct",
        label="Qwen 2.5 72B",
        description="Most capable free model — strong reasoning, coding, and tool use. Supports all MCP capabilities.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="Qwen/Qwen2.5-32B-Instruct",
        label="Qwen 2.5 32B",
        description="Large model with strong tool use and reasoning. Good balance of capability and speed.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="Qwen/Qwen2.5-14B-Instruct",
        label="Qwen 2.5 14B",
        description="Mid-size model — fast responses with reliable tool use. Good for most agents.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="Qwen/Qwen2.5-7B-Instruct",
        label="Qwen 2.5 7B",
        description="Fastest free model — lightweight but still supports tool calling. Best for simple agents.",
        available=True,
    ),
    # --- Featherless AI — reasoning / frontier open models ---
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="deepseek-ai/DeepSeek-V3.2",
        label="DeepSeek V3.2",
        description="DeepSeek's latest flagship — top-tier reasoning and tool use with a very large context window. Best free model for hard, multi-step agents.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="deepseek-ai/DeepSeek-V3.1-Terminus",
        label="DeepSeek V3.1 Terminus",
        description="Stable, heavily-tested DeepSeek release — excellent reasoning and reliable tool calling.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="Qwen/Qwen3-Coder-480B-A35B-Instruct",
        label="Qwen 3 Coder 480B",
        description="Qwen's largest agentic coding model — the strongest tool user in the catalog. Best for agents that chain many capability calls.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="Qwen/Qwen3-Coder-30B-A3B-Instruct",
        label="Qwen 3 Coder 30B",
        description="Mixture-of-experts coding model — strong tool use at a fraction of the 480B's cost and latency.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="mistralai/Mistral-Large-Instruct-2411",
        label="Mistral Large",
        description="Mistral's flagship open model — strong general reasoning with dependable function calling.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="mistralai/Mistral-Medium-3.5-128B",
        label="Mistral Medium 3.5",
        description="Mid-size Mistral with a 128K context window — good for agents that need to hold a lot of material at once.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="NousResearch/Hermes-4-70B",
        label="Hermes 4 70B",
        description="Nous Research's tool-use-tuned Llama — built specifically for agentic workflows and structured output.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="NousResearch/Hermes-4-14B",
        label="Hermes 4 14B",
        description="Smaller Hermes 4 — keeps the agentic tool-use tuning with faster, cheaper responses.",
        available=True,
    ),
    ModelOption(
        provider="featherless",
        provider_label="Featherless AI",
        model_id="Qwen/Qwen3-4B-Instruct-2507",
        label="Qwen 3 4B",
        description="Very fast small model that still emits proper tool calls. Best when latency matters more than depth.",
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
    # --- Meta (Llama) — open-weight; run via Groq above. Listed here as its
    # own family for browsing. ---
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
    CapabilityOption(
        key="image_recognition",
        name="Image Recognition",
        description="Lets the agent see and analyze images you upload in chat. Works with any model — models that can't read images directly get a written description from a vision model instead.",
        icon="🖼️",
        wired=True,
        mcp_server=None,
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
