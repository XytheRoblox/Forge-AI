import os
import re
from typing import Optional

from groq import Groq

_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_thinking(text: str) -> str:
    """Some reasoning models (e.g. Groq's qwen/qwen3.6-27b) emit their chain
    of thought directly in `content` wrapped in <think> tags, rather than in
    a separate `reasoning` field — strip it so it doesn't leak into output
    meant to be a clean answer (a manifesto's expanded system prompt)."""
    return _THINK_BLOCK.sub("", text).strip()

_groq_client: Optional[Groq] = None


def _get_groq() -> Groq:
    global _groq_client
    if _groq_client is None:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY is not set. Add it to backend/.env to use Groq models."
            )
        _groq_client = Groq(api_key=api_key)
    return _groq_client


MANIFESTO_EXPANSION_PROMPT = """You turn a short, informal description of an AI agent's \
purpose into a complete, precise system prompt that makes it behave like a dedicated, \
task-focused agent — not a generic open-ended chatbot.

The user's one-line manifesto is:
---
{manifesto}
---

Write a system prompt that:
- Opens by stating the agent's specific role and purpose in one or two sentences — no generic \
"I'm an AI assistant, how can I help you today?" framing.
- Explicitly scopes the agent to that purpose: it should stay focused on the task, proactively \
pursue it rather than passively waiting to be told each step, and briefly redirect if asked to do \
something clearly outside its stated purpose.
- If tools/capabilities are available to it, instructs it to actually use them to get real \
information or take real action, rather than describing what it could do.
- Sets a direct, efficient tone appropriate to the task — infer the right tone from the manifesto \
itself (e.g. playful for a trivia bot, precise for a data-lookup bot, warm for a concierge bot).
- Stays under 200 words.

Respond with ONLY the system prompt text, no preamble or explanation."""


MANIFESTO_EXPANSION_MODEL = "llama-3.3-70b-versatile"


RECOMMEND_MODEL = "llama-3.3-70b-versatile"

RECOMMEND_PROMPT = """Pick the best model for an AI agent with this purpose:
---
{purpose}
---

The available models, one per line as `id — description`:
{catalog}

Choose based on what the purpose actually demands. Reasoning-heavy work (maths, physics,
analysis, planning, multi-step tool use) needs a strong model even though it costs latency.
Simple, high-volume, or latency-sensitive work is better served by a small fast one. Coding
agents suit the coder models.

Respond with ONLY a JSON object, no markdown fence:
{{"model_id": "<exact id copied from the list above>", "reason": "<one sentence, under 20 words, addressed to the user>"}}"""


THEME_MODEL = "llama-3.3-70b-versatile"

THEME_PROMPT = """You are designing the visual theme for a single-purpose AI agent's chat page.

The agent is called "{name}" and its purpose is:
---
{purpose}
---

Design a theme that visually evokes that specific subject, so the page feels made for this
agent rather than generic. A math tutor should feel like mathematics (chalkboard greens,
graph-paper grids, formula motifs); a chef agent should feel culinary; a security agent
should feel like a terminal. Be bold and specific — commit to the subject.

What each key means:
- accent        the primary accent color
- bg            page background for LIGHT mode (must be light)
- text          body text for light mode, readable on bg
- text_h        heading text for light mode, darker than text
- border        subtle border for light mode
- code_bg       code/quote background for light mode
- dark_bg       page background for DARK mode (must be dark)
- dark_text     body text for dark mode, readable on dark_bg
- dark_text_h   heading text for dark mode, lighter than dark_text
- dark_border   subtle border for dark mode
- dark_code_bg  code background for dark mode
- pattern       a subtle repeating background motif; exactly one of:
                none, grid, dots, diagonal, waves
- pattern_color the motif's color; keep it very close to bg or it overpowers the text
- font          exactly one of: sans, serif, mono, rounded
- tagline       a short subtitle for the page header, under 60 characters

Contrast rules, which matter more than style: text on bg and dark_text on dark_bg must be
comfortably readable. Never use a light bg with light text, or a dark bg with dark text.

Respond with ONLY a JSON object — no markdown fence, no commentary, and no explanations
inside the values. Every color must be a bare 6-digit hex string and nothing else. Match
this shape exactly:
{{"accent": "#2E7D32", "bg": "#F4F6F2", "text": "#4A5247", "text_h": "#14200F",
 "border": "#D5DED1", "code_bg": "#E8EEE4", "dark_bg": "#101711", "dark_text": "#A9B6A5",
 "dark_text_h": "#EAF2E6", "dark_border": "#26332A", "dark_code_bg": "#18211A",
 "pattern": "grid", "pattern_color": "#E2E9DE", "font": "mono",
 "tagline": "Working through it, one step at a time"}}"""

# Deliberately a search, not a full match. Models like to annotate their
# values ("#03A9F4 — the primary accent color"), and a strict ^...$ check
# rejects every colour in that case and silently falls back to the default
# theme for the whole page. Pulling the first hex triple out of the string is
# just as safe — the extracted value is still validated by construction — and
# far more forgiving of a chatty model.
_HEX = re.compile(r"#[0-9a-fA-F]{6}\b")

# Same reasoning for the enum fields: accept "grid" out of "grid — a subtle
# graph-paper motif" rather than discarding it.
def _first_choice(value: str, allowed) -> Optional[str]:
    lowered = value.lower()
    for option in allowed:
        if re.search(rf"\b{option}\b", lowered):
            return option
    return None

_FONT_STACKS = {
    "sans": 'system-ui, "Segoe UI", Roboto, sans-serif',
    "serif": 'Georgia, "Iowan Old Style", "Times New Roman", serif',
    "mono": '"SF Mono", ui-monospace, Menlo, Consolas, monospace',
    "rounded": '"Nunito", "Quicksand", ui-rounded, "Segoe UI", sans-serif',
}

# Each motif is a fixed CSS recipe; the model only picks WHICH one and its
# color. That keeps a decorative background from ever becoming arbitrary CSS.
_PATTERNS = {
    "none": "none",
    "grid": (
        "linear-gradient({c} 1px, transparent 1px), "
        "linear-gradient(90deg, {c} 1px, transparent 1px)"
    ),
    "dots": "radial-gradient({c} 1.5px, transparent 1.6px)",
    "diagonal": "repeating-linear-gradient(45deg, {c} 0 2px, transparent 2px 12px)",
    "waves": (
        "repeating-radial-gradient(circle at 50% 100%, {c} 0 1px, transparent 1px 18px)"
    ),
}

_PATTERN_SIZES = {
    "none": "auto",
    "grid": "28px 28px",
    "dots": "22px 22px",
    "diagonal": "auto",
    "waves": "auto",
}

_THEME_FALLBACK = {
    "accent": "#aa3bff",
    "bg": "#ffffff", "text": "#6b6375", "text_h": "#08060d",
    "border": "#e5e4e7", "code_bg": "#f4f3ec",
    "dark_bg": "#16171d", "dark_text": "#9ca3af", "dark_text_h": "#f3f4f6",
    "dark_border": "#2e303a", "dark_code_bg": "#1f2028",
    "pattern": "none", "pattern_color": "#ffffff",
    "font": "sans", "tagline": "",
}


def _coerce_theme(raw: dict) -> dict:
    """Keep only values that are safe and well-formed, falling back per-field.

    The model's output lands in a <style> block, so nothing here is trusted:
    colors must match a strict hex pattern, and `pattern`/`font` must be one
    of the fixed recipes above. A field that fails validation is replaced with
    the default rather than rejecting the whole theme, so one bad color can't
    cost the agent its entire look."""
    theme = dict(_THEME_FALLBACK)
    for key, default in _THEME_FALLBACK.items():
        value = raw.get(key)
        if not isinstance(value, str):
            continue
        value = value.strip()
        if key == "pattern":
            choice = _first_choice(value, _PATTERNS)
            if choice:
                theme[key] = choice
        elif key == "font":
            choice = _first_choice(value, _FONT_STACKS)
            if choice:
                theme[key] = choice
        elif key == "tagline":
            # Rendered as text, escaped by the caller; only length is enforced.
            theme[key] = value[:60]
        else:
            found = _HEX.search(value)
            if found:
                theme[key] = found.group(0)
    return theme


def generate_theme(name: str, purpose: str) -> dict:
    """Ask the platform's Groq key for a subject-appropriate theme spec.

    Returns a fully-populated, validated theme dict — never raises for a bad
    or unparseable model response, since a page that renders in default colors
    is a much better outcome than a build that fails over decoration."""
    import json

    try:
        client = _get_groq()
        response = client.chat.completions.create(
            model=THEME_MODEL,
            max_tokens=900,
            messages=[
                {
                    "role": "user",
                    "content": THEME_PROMPT.format(name=name or "Agent", purpose=purpose or "a helpful assistant"),
                }
            ],
        )
        text = _strip_thinking(response.choices[0].message.content or "")
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            return dict(_THEME_FALLBACK)
        return _coerce_theme(json.loads(text[start : end + 1]))
    except Exception:  # noqa: BLE001 - decoration must never fail a build
        return dict(_THEME_FALLBACK)


def theme_css(theme: dict) -> str:
    """Render a validated theme dict into the CSS the page overrides with."""
    pattern = theme["pattern"]
    # The motif is drawn from a variable rather than the raw colour so dark
    # mode can substitute its own. A colour picked to sit just off a LIGHT
    # background is, by construction, a high-contrast glare against a dark
    # one — so dark mode derives a faint tint from the text colour instead of
    # reusing the model's light-mode choice.
    layer = _PATTERNS[pattern].format(c="var(--pattern-color)")
    size = _PATTERN_SIZES[pattern]
    # NB: only gradients may appear in background-image. Appending
    # `var(--bg)` here (a colour, not an image) invalidates the whole
    # declaration and silently drops the pattern; the base rule's
    # `background: var(--bg)` already paints the colour underneath.
    # --accent is deliberately NOT set here. The runtime substitutes
    # __ACCENT_COLOR__ from theme.json on every request, which is what the
    # accent picker writes — emitting it in this later block would silently
    # override the user's choice. Callers persist theme["accent"] into
    # theme.json instead, so the generated accent and the picker stay the
    # same single value.
    return f""":root {{
    --bg: {theme['bg']};
    --text: {theme['text']};
    --text-h: {theme['text_h']};
    --border: {theme['border']};
    --code-bg: {theme['code_bg']};
    --accent-bg: color-mix(in srgb, var(--accent) 12%, transparent);
    --pattern-color: {theme['pattern_color']};
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: {theme['dark_bg']};
      --text: {theme['dark_text']};
      --text-h: {theme['dark_text_h']};
      --border: {theme['dark_border']};
      --code-bg: {theme['dark_code_bg']};
      --accent-bg: color-mix(in srgb, var(--accent) 20%, transparent);
      --pattern-color: color-mix(in srgb, var(--text) 14%, transparent);
    }}
  }}
  body {{
    font-family: {_FONT_STACKS[theme['font']]};
    background-image: {'none' if pattern == 'none' else layer};
    background-size: {size};
    background-attachment: fixed;
  }}"""


def recommend_model(purpose: str, options: list) -> Optional[dict]:
    """Suggest a model for this agent's stated purpose.

    `options` is the live catalog, so the suggestion can only ever be a model
    that's actually on offer — the returned id is checked against it rather
    than trusted, since a model inventing a plausible-looking id would put the
    wizard into a state the user can't act on. Returns None when there's
    nothing useful to say, which the caller shows as "no recommendation"
    rather than a wrong one."""
    import json

    available = [o for o in options if o.available]
    if not available:
        return None
    catalog = "\n".join(f"{o.model_id} — {o.label}: {o.description}" for o in available)
    try:
        client = _get_groq()
        response = client.chat.completions.create(
            model=RECOMMEND_MODEL,
            max_tokens=300,
            messages=[
                {"role": "user", "content": RECOMMEND_PROMPT.format(purpose=purpose, catalog=catalog)}
            ],
        )
        text = _strip_thinking(response.choices[0].message.content or "")
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            return None
        parsed = json.loads(text[start : end + 1])
    except Exception:  # noqa: BLE001 - a missing suggestion is not an error
        return None

    chosen = next((o for o in available if o.model_id == parsed.get("model_id")), None)
    if chosen is None:
        return None
    reason = str(parsed.get("reason") or "").strip()
    return {
        "model_id": chosen.model_id,
        "provider": chosen.provider,
        "label": chosen.label,
        "reason": reason[:160],
    }


def expand_manifesto(manifesto: str) -> str:
    """Expand a one-line manifesto into a full system prompt.

    This always runs on the platform's own Groq key rather than the agent's
    chosen model provider — it's a build-time platform operation, not
    something the deployed agent itself does, so it shouldn't require (or
    burn) whatever API key the agent's own owner supplies for their model.
    """
    prompt = MANIFESTO_EXPANSION_PROMPT.format(manifesto=manifesto)
    client = _get_groq()
    response = client.chat.completions.create(
        model=MANIFESTO_EXPANSION_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return _strip_thinking(response.choices[0].message.content)
