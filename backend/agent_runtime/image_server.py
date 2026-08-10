"""MCP server for generating images.

Runs as a stdio subprocess inside the agent's own container, like the other
agent-hosted capabilities.

Uses Pollinations, which needs no API key. That's the deciding factor rather
than an aesthetic preference: every other option (OpenAI, Stability, Replicate,
fal) requires its own paid account, and a capability that only works once
someone has signed up for a third service isn't one an agent can be given by
default. A keyed provider can be added later behind the same tool.
"""

import os
import time
import urllib.parse

import httpx
from mcp.server.fastmcp import FastMCP

ENDPOINT = "https://image.pollinations.ai/prompt/"

# Generation is slow — the image is rendered on request, not looked up.
REQUEST_TIMEOUT = 180.0

mcp = FastMCP("Image Generation")


@mcp.tool()
def generate_image(prompt: str, width: int = 1024, height: int = 1024) -> str:
    """Generate an image from a text description and return it for display.

    Describe the subject, style and composition in the prompt — "a cutaway
    diagram of a volcano, textbook illustration style, labelled" works far
    better than "volcano". Sizes are clamped to 256-1536.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return "Error: a prompt is required to generate an image."

    width = max(256, min(int(width or 1024), 1536))
    height = max(256, min(int(height or 1024), 1536))
    # A seed makes repeat calls with the same prompt return different images
    # rather than the cached first one, so "try another" actually does.
    seed = int(time.time() * 1000) % 1_000_000

    url = (
        ENDPOINT
        + urllib.parse.quote(prompt, safe="")
        + f"?width={width}&height={height}&seed={seed}&nologo=true"
    )

    # Fetched here rather than handed over unverified: the URL renders on
    # request, so returning it blind would mean an agent confidently showing a
    # link that turns out to be an error page.
    try:
        response = httpx.get(url, timeout=REQUEST_TIMEOUT, follow_redirects=True)
    except httpx.HTTPError as exc:
        return f"Error: the image service could not be reached ({exc})."

    if response.status_code != 200:
        return f"Error: the image service returned {response.status_code}."
    if not response.headers.get("content-type", "").startswith("image/"):
        return "Error: the image service returned something that wasn't an image."

    # Markdown, so the chat page renders it inline instead of showing a link.
    return f"![{prompt}]({url})\n\n(Generated {width}x{height}.)"


if __name__ == "__main__":
    mcp.run(transport="stdio")
