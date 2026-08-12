"""Where Forge is reachable from, which is not always localhost.

Several things have to name an address that somebody else's browser will
resolve: the OAuth redirect Google sends a user back to, and the URLs the
graphing tool puts in an agent's replies. Hard-coding localhost is right on a
laptop and wrong the moment the app is shared, and the failure is quiet — a
redirect that lands on the visitor's own machine, an image that never loads.

So "deployment mode" is a single question — what is this instance's public
base URL? — answered in three ways, most explicit first:

1. PUBLIC_BASE_URL, if set. Always wins, and is what a real deployment uses.
2. The running ngrok tunnel, when FORGE_PUBLIC_MODE=ngrok. Read from ngrok's
   own local API, because a free tunnel gets a new hostname every restart and
   pasting it into .env each time is a step people forget.
3. Otherwise localhost, exactly as before.
"""

import os

import httpx

# ngrok's agent publishes its current tunnels here. Local, so a short timeout
# is generous, and any failure just means falling back to localhost.
NGROK_API = "http://127.0.0.1:4040/api/tunnels"

LOCAL_BACKEND = "http://localhost:8000"

_cached: tuple[str, str] | None = None  # (mode, url)


def _from_ngrok() -> str | None:
    try:
        response = httpx.get(NGROK_API, timeout=2.0)
        response.raise_for_status()
        tunnels = response.json().get("tunnels") or []
    except (httpx.HTTPError, ValueError):
        return None
    for tunnel in tunnels:
        url = tunnel.get("public_url") or ""
        if url.startswith("https://"):
            return url.rstrip("/")
    return None


def mode() -> str:
    if os.environ.get("PUBLIC_BASE_URL", "").strip():
        return "explicit"
    return (os.environ.get("FORGE_PUBLIC_MODE") or "local").strip().lower()


def base_url() -> str:
    """The origin an outside browser should use to reach this instance."""
    global _cached
    explicit = os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")
    if explicit:
        return explicit

    if mode() == "ngrok":
        # Cached because this is called per OAuth start and per agent build,
        # and a tunnel's hostname only changes when ngrok restarts. A miss
        # falls through rather than failing the request.
        if _cached and _cached[0] == "ngrok":
            return _cached[1]
        found = _from_ngrok()
        if found:
            _cached = ("ngrok", found)
            return found

    # Deliberately below the mode check. PUBLIC_BACKEND_URL predates this and
    # is set to localhost in most existing .env files, so honouring it first
    # would mean switching to ngrok mode silently did nothing — which is the
    # confusing half-configured state this module exists to prevent.
    legacy = os.environ.get("PUBLIC_BACKEND_URL", "").strip().rstrip("/")
    return legacy or LOCAL_BACKEND


def refresh() -> str:
    """Forget a cached tunnel and look again — for when ngrok was restarted."""
    global _cached
    _cached = None
    return base_url()


def describe() -> dict:
    """Enough for the UI to say where this instance thinks it lives."""
    url = base_url()
    return {"mode": mode(), "base_url": url, "public": not url.startswith(LOCAL_BACKEND)}
