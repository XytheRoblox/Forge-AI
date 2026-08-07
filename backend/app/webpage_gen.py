import html as html_lib
from pathlib import Path

TEMPLATE_PATH = Path(__file__).resolve().parent.parent / "agent_runtime" / "web" / "template.html"


def _purpose_line(agent) -> str:
    if agent.manifesto:
        line = agent.manifesto.strip().splitlines()[0]
        return line if len(line) <= 140 else line[:137].rstrip() + "…"
    return "Ask it anything."


def generate_webpage(agent) -> str:
    """Deterministically build the agent's chat page from the shared template.

    No LLM is involved: only the name/purpose text is substituted, so the
    chat functionality, rich-text rendering, and placeholder-based settings
    (accent color, image upload) defined in template.html can never be
    broken by model output.
    """
    html = TEMPLATE_PATH.read_text()
    name = html_lib.escape(agent.name or "Agent")
    purpose = html_lib.escape(_purpose_line(agent))

    html = html.replace("<title>Agent</title>", f"<title>{name}</title>", 1)
    html = html.replace("<h1>Agent</h1>", f"<h1>{name}</h1>", 1)
    html = html.replace("<p>Ask it anything.</p>", f"<p>{purpose}</p>", 1)

    return html
