"""MCP server for graphing, offered to agents as "Desmos Graphing".

Two tools, because there are two different jobs:

`plot_graph` emits a spec the agent's chat page turns into a real, interactive
Desmos calculator the user can pan, zoom and trace. Desmos is a browser
library, not a web service — there is no endpoint to POST an equation to and
get a picture back — so nothing is drawn here.

`graph_image` renders an actual PNG. That's for everywhere the interactive
calculator can't go: a reply delivered through a custom API endpoint, a page
without the Desmos script, or a caller that wants a picture it can save and
send on. It's also the only one of the two the agent's own vision layer can
look at, since a spec isn't something you can see.

Runs as one shared SSE container rather than a subprocess per agent. Nothing
here is per-agent: there's no credential to keep separate, no filesystem to
isolate, and the output depends only on the arguments.
"""

import json
import math
import os
import re
import time
import uuid
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # No display in a container; must be set before pyplot.

import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from mcp.server.fastmcp import FastMCP  # noqa: E402
from starlette.responses import FileResponse, JSONResponse  # noqa: E402

MAX_EXPRESSIONS = 12

# Rendered PNGs live here and are served back over this container's own port.
# A data URI would be simpler, but the tool's return value goes into the
# model's context, where a base64 PNG would blow the prompt budget and be
# truncated into a broken image.
GRAPH_DIR = Path("/tmp/graphs")
GRAPH_DIR.mkdir(parents=True, exist_ok=True)

# How the browser reaches this container. The chat page runs in the user's
# browser, not on the Docker network, so a container-name URL would not
# resolve — this has to be a host-reachable address, which is why the port is
# published on a fixed number rather than an ephemeral one.
PUBLIC_URL = os.environ.get("DESMOS_PUBLIC_URL", "http://localhost:8788").rstrip("/")

# Old renders are only needed until the page fetches them, but a chat stays
# open for a while, so keep a generous window rather than deleting on read.
MAX_STORED_GRAPHS = 200

mcp = FastMCP("Desmos", host="0.0.0.0", port=8000)


# --- expression handling -------------------------------------------------

# Every name an expression is allowed to mention. Anything else is rejected
# rather than evaluated: these strings arrive from a language model, and the
# evaluation below is a real eval, so the allowlist is the security boundary.
_ALLOWED_NAMES = {
    "x": None,  # filled per-evaluation with the sample points
    "pi": math.pi,
    "e": math.e,
    "sin": np.sin, "cos": np.cos, "tan": np.tan,
    "asin": np.arcsin, "acos": np.arccos, "atan": np.arctan,
    "arcsin": np.arcsin, "arccos": np.arccos, "arctan": np.arctan,
    "sinh": np.sinh, "cosh": np.cosh, "tanh": np.tanh,
    "exp": np.exp, "log": np.log, "ln": np.log, "log10": np.log10,
    "sqrt": np.sqrt, "abs": np.abs, "floor": np.floor, "ceil": np.ceil,
}

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
# Strips the "y=" / "f(x)=" that Desmos syntax puts on the front.
_ASSIGNMENT = re.compile(r"^\s*(?:y|f\s*\(\s*x\s*\)|[a-z]\s*\(\s*x\s*\))\s*=", re.IGNORECASE)


def _normalise(expression: str) -> str:
    """Desmos/LaTeX-ish input to something Python can evaluate."""
    text = expression.strip()
    text = _ASSIGNMENT.sub("", text, count=1)
    text = text.replace("\\left", "").replace("\\right", "")
    text = re.sub(r"\\(?=[a-zA-Z])", "", text)  # \sin -> sin
    text = text.replace("^", "**")
    text = re.sub(r"\{([^{}]*)\}", r"(\1)", text)  # \frac-free braces
    # Implicit multiplication, which every calculator accepts and Python
    # doesn't: 2x, 3(x+1), )( .
    text = re.sub(r"(\d)\s*([A-Za-z(])", r"\1*\2", text)
    text = re.sub(r"\)\s*(\()", r")*\1", text)
    text = re.sub(r"\)\s*([A-Za-z0-9])", r")*\1", text)
    return text.strip()


def _evaluate(expression: str, xs: np.ndarray):
    """Sample an expression over xs, or raise ValueError explaining why not."""
    text = _normalise(expression)
    if not text:
        raise ValueError("empty expression")
    for name in set(_IDENTIFIER.findall(text)):
        if name not in _ALLOWED_NAMES:
            raise ValueError(f"unknown name {name!r}")
    env = {k: v for k, v in _ALLOWED_NAMES.items() if v is not None}
    env["x"] = xs
    try:
        with np.errstate(all="ignore"):
            values = eval(text, {"__builtins__": {}}, env)  # noqa: S307 - names are allowlisted
    except Exception as exc:  # noqa: BLE001 - reported to the caller, not raised
        raise ValueError(str(exc)) from exc
    values = np.asarray(values, dtype=float) * np.ones_like(xs)
    # A vertical asymptote otherwise becomes a near-vertical line joining
    # +inf to -inf, which reads as part of the curve.
    values[~np.isfinite(values)] = np.nan
    return values


def _prune() -> None:
    files = sorted(GRAPH_DIR.glob("*.png"), key=lambda p: p.stat().st_mtime)
    for stale in files[:-MAX_STORED_GRAPHS]:
        stale.unlink(missing_ok=True)


# --- tools ---------------------------------------------------------------


@mcp.tool()
def plot_graph(expressions: list[str], title: str = "") -> str:
    """Plot expressions on an interactive Desmos graph the user can explore.

    Pass Desmos/LaTeX-style expressions exactly as they'd be typed into the
    calculator — "y=x^2", "f(x)=\\\\sin(x)", "y=2x+1". Several can be plotted
    together to compare them. The user gets a live graph they can zoom and
    trace, so prefer this over describing the shape of a curve in words. Use
    graph_image instead when the answer needs to be a picture — an emailed
    reply, an API response, or anything you need to look at yourself.
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


@mcp.tool()
def graph_image(
    expressions: list[str],
    title: str = "",
    x_min: float = -10.0,
    x_max: float = 10.0,
) -> str:
    """Render expressions as a PNG image of the graph, and attach it.

    Same expression syntax as plot_graph ("y=x^2", "f(x)=sin(x)", "y=2x+1"),
    plotted over x_min..x_max. Returns the image as markdown, which the page
    displays inline — include it in your reply as-is. Use this when the answer
    needs to be an actual picture rather than a calculator the user drives:
    a reply going out through an API endpoint, or a graph you want to examine
    yourself before describing it.
    """
    if isinstance(expressions, str):
        expressions = [expressions]
    cleaned = [e.strip() for e in (expressions or []) if isinstance(e, str) and e.strip()]
    if not cleaned:
        return "Error: at least one expression is required, e.g. expressions=[\"y=x^2\"]."
    if len(cleaned) > MAX_EXPRESSIONS:
        return f"Error: too many expressions ({len(cleaned)}); plot at most {MAX_EXPRESSIONS}."
    try:
        x_min, x_max = float(x_min), float(x_max)
    except (TypeError, ValueError):
        return "Error: x_min and x_max must be numbers."
    if not (math.isfinite(x_min) and math.isfinite(x_max)) or x_min >= x_max:
        return "Error: x_min must be a number smaller than x_max."

    xs = np.linspace(x_min, x_max, 2000)
    figure, axes = plt.subplots(figsize=(7, 4.5), dpi=130)
    plotted, failures = 0, []
    for expression in cleaned:
        try:
            axes.plot(xs, _evaluate(expression, xs), linewidth=2, label=expression)
            plotted += 1
        except ValueError as exc:
            failures.append(f"{expression} ({exc})")

    if not plotted:
        plt.close(figure)
        return "Error: none of those expressions could be plotted — " + "; ".join(failures)

    axes.axhline(0, color="#888", linewidth=0.8)
    axes.axvline(0, color="#888", linewidth=0.8)
    axes.grid(True, linestyle=":", alpha=0.5)
    axes.set_xlabel("x")
    axes.set_ylabel("y")
    if title.strip():
        axes.set_title(title.strip())
    axes.legend(loc="best", fontsize=9)
    figure.tight_layout()

    name = f"{int(time.time())}-{uuid.uuid4().hex[:8]}.png"
    figure.savefig(GRAPH_DIR / name, format="png")
    plt.close(figure)
    _prune()

    alt = title.strip() or ", ".join(cleaned)
    note = f"\n\nCould not plot: {'; '.join(failures)}." if failures else ""
    return f"![{alt}]({PUBLIC_URL}/graphs/{name})\n\nRendered {plotted} expression(s).{note}"


# --- serving the rendered images -----------------------------------------


@mcp.custom_route("/graphs/{name}", methods=["GET"])
async def serve_graph(request):
    """Hand back a rendered PNG.

    The name is matched against a strict pattern rather than joined onto the
    directory: this route is reachable from the browser, and a name is only
    ever one this server generated."""
    name = request.path_params["name"]
    if not re.fullmatch(r"\d+-[0-9a-f]{8}\.png", name):
        return JSONResponse({"error": "not found"}, status_code=404)
    path = GRAPH_DIR / name
    if not path.is_file():
        return JSONResponse({"error": "not found"}, status_code=404)
    return FileResponse(path, media_type="image/png")


if __name__ == "__main__":
    mcp.run(transport="sse")
