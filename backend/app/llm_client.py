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
