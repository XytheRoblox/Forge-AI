import base64
import html as html_lib
import json
import mimetypes
from pathlib import Path

from app import llm_client

WEB_DIR = Path(__file__).resolve().parent.parent / "agent_runtime" / "web"
TEMPLATE_PATH = WEB_DIR / "template.html"
LOGO_DIR = WEB_DIR / "logos"

# Kept small deliberately: every logo is base64'd into every generated page, so
# a stray 2MB PNG would bloat each agent's HTML. Anything larger is skipped in
# favour of the capability's emoji.
MAX_LOGO_BYTES = 64 * 1024


def _tool_logos() -> dict[str, str]:
    """Capability key -> data URI, for every usable file in web/logos.

    The agent container serves a single self-contained HTML file and has no
    static asset route, so a logo can only reach the page by travelling inside
    it. Missing, oversized, or unrecognised files are simply absent from the
    map, and the page falls back to the emoji for those capabilities."""
    logos: dict[str, str] = {}
    if not LOGO_DIR.is_dir():
        return logos
    for path in sorted(LOGO_DIR.iterdir()):
        if path.suffix.lower() not in (".svg", ".png", ".jpg", ".jpeg", ".webp"):
            continue
        try:
            raw = path.read_bytes()
        except OSError:
            continue
        if not raw or len(raw) > MAX_LOGO_BYTES:
            continue
        mime = mimetypes.types_map.get(path.suffix.lower()) or "image/svg+xml"
        logos[path.stem] = f"data:{mime};base64,{base64.b64encode(raw).decode()}"
    return logos


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
    # JSON-encoded so it drops straight into a <script> as a literal. Encoding
    # `<` keeps a data URI from ever closing the script tag early.
    logos = json.dumps(_tool_logos()).replace("<", "\\u003c")
    html = html.replace("__TOOL_LOGOS__", logos, 1)

    return html, theme
