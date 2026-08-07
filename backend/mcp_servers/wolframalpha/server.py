import os

import httpx
from mcp.server.fastmcp import FastMCP

APP_ID = os.environ.get("WOLFRAM_ALPHA_APP_ID", "")

mcp = FastMCP("WolframAlpha", host="0.0.0.0", port=8000)


@mcp.tool()
def ask_wolfram_alpha(query: str, app_id: str = "") -> str:
    """Ask Wolfram|Alpha a computational, math, science, unit-conversion, or
    factual question and get back a short, direct answer (e.g. "what is the
    square root of 144", "distance from Earth to Mars", "GDP of France")."""
    effective_app_id = app_id or APP_ID
    if not effective_app_id:
        return "WolframAlpha is not configured: no app_id was provided for this request."

    try:
        response = httpx.get(
            "https://api.wolframalpha.com/v1/result",
            params={"appid": effective_app_id, "i": query},
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        return f"Could not reach Wolfram|Alpha: {exc}"

    if response.status_code == 200:
        return response.text
    if response.status_code == 501:
        return f"Wolfram|Alpha couldn't compute an answer for: {query!r}"
    return f"Wolfram|Alpha error ({response.status_code}): {response.text}"


if __name__ == "__main__":
    mcp.run(transport="sse")
