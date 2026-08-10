"""MCP server for plotting graphs with Desmos.

Desmos is a browser library, not a web service — there is no endpoint to POST
an equation to and get a picture back. So this tool doesn't draw anything; it
emits a spec that the agent's chat page turns into a real, interactive Desmos
calculator the user can pan, zoom and trace.

That's better than a static image for the thing this is usually for: a student
looking at f(x) and f'(x) together learns more from dragging the graph than
from a screenshot of it.
"""

import json

from mcp.server.fastmcp import FastMCP

MAX_EXPRESSIONS = 12

mcp = FastMCP("Desmos")


@mcp.tool()
def plot_graph(expressions: list[str], title: str = "") -> str:
    """Plot one or more expressions on an interactive Desmos graph.

    Pass Desmos/LaTeX-style expressions exactly as they'd be typed into the
    calculator — "y=x^2", "f(x)=\\\\sin(x)", "y=2x+1". Several can be plotted
    together to compare them. The user gets a live graph they can zoom and
    trace, so prefer this over describing the shape of a curve in words.
    """
    if isinstance(expressions, str):
        expressions = [expressions]
    cleaned = [e.strip() for e in (expressions or []) if isinstance(e, str) and e.strip()]
    if not cleaned:
        return "Error: at least one expression is required, e.g. expressions=[\"y=x^2\"]."
    if len(cleaned) > MAX_EXPRESSIONS:
        return f"Error: too many expressions ({len(cleaned)}); plot at most {MAX_EXPRESSIONS}."

    # A fenced block rather than prose: the page can find it unambiguously,
    # and a model that pastes it verbatim into its reply gets the graph
    # rendered rather than showing the user raw JSON.
    spec = json.dumps({"title": title.strip(), "expressions": cleaned})
    return f"```desmos\n{spec}\n```\n\nPlotted {len(cleaned)} expression(s)."


if __name__ == "__main__":
    mcp.run(transport="stdio")
