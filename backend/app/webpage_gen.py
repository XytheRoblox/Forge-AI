import html as html_lib
from pathlib import Path

from app import llm_client

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "agent_runtime" / "web" / "template.html"


def _purpose_line(agent) -> str:
    if agent.manifesto:
        line = agent.manifesto.strip().splitlines()[0]
        return line if len(line) <= 140 else line[:137].rstrip() + "…"
    return "Ask it anything."


def _theme_source(agent) -> str:
    """The best available description of what this agent is for — the theme is
    only as on-topic as this text is."""
    return (agent.manifesto or agent.system_prompt or agent.name or "").strip()


def generate_webpage(agent, themed: bool = True) -> tuple[str, dict]:
    """Build the agent's chat page from the shared template.

    The page's STRUCTURE is always deterministic: only text and a validated
    theme are substituted, so chat, rich-text rendering, and image upload can
    never be broken by model output.

    Within that, `themed=True` asks a model to design a look that suits this
    specific agent (a math tutor gets chalkboard greens and a graph-paper
    grid; a chef gets something culinary). What comes back is a constrained
    spec — hex colors, one of a fixed set of patterns, one of a fixed set of
    font stacks — which llm_client validates field-by-field before it becomes
    CSS. A failed or unparseable response silently yields the default theme
    rather than failing the build.

    __ACCENT_COLOR__ and __IMAGE_UPLOAD_ENABLED__ are intentionally left in
    place: the runtime substitutes those on every request from theme.json and
    features.json, so the accent picker and capability toggles keep working
    without regenerating the page.

    Returns (html, theme) — the theme comes back so the caller can persist its
    accent into theme.json, which is what actually drives --accent.
    """
    html = TEMPLATE_PATH.read_text()
    name = html_lib.escape(agent.name or "Agent")
    purpose = html_lib.escape(_purpose_line(agent))

    theme = (
        llm_client.generate_theme(agent.name or "Agent", _theme_source(agent))
        if themed
        else dict(llm_client._THEME_FALLBACK)
    )

    # A generated tagline is more evocative than the raw manifesto line, but
    # only if the model actually produced one.
    tagline = html_lib.escape(theme.get("tagline") or "") or purpose

    html = html.replace("<title>Agent</title>", f"<title>{name}</title>", 1)
    html = html.replace("<h1>Agent</h1>", f"<h1>{name}</h1>", 1)
    html = html.replace("<p>Ask it anything.</p>", f"<p>{tagline}</p>", 1)
    html = html.replace("__AGENT_THEME_CSS__", llm_client.theme_css(theme), 1)

    return html, theme
