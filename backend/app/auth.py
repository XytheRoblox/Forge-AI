"""A shared-secret gate for the API.

Forge is normally a localhost tool, where the operating system is the access
control. The moment it's put behind a tunnel that stops being true, and what's
on the other side is not a read-only demo: the API creates Docker containers,
writes files into them, can run code inside them via the Code Execution
capability, and spends the platform's model and capability API keys. Anyone
who found the URL could do all of that.

CORS is not a substitute. It restrains browsers on other origins; it does
nothing to a curl or a script, which is what an opportunistic scan of a public
tunnel actually is.

So: one token, required on every /api route. Set FORGE_ACCESS_TOKEN and the
gate turns on. Leave it unset and the gate stays off — but then only loopback
requests are served, so forgetting to set it before opening a tunnel fails
closed rather than silently exposing everything.
"""

import hmac
import os

from fastapi import Request
from fastapi.responses import JSONResponse

TOKEN_ENV = "FORGE_ACCESS_TOKEN"
HEADER_NAME = "x-forge-token"
COOKIE_NAME = "forge_access"
QUERY_NAME = "access_token"

# Everything else is guarded. Health is left open so a tunnel or uptime check
# can see the app is alive without holding the secret.
OPEN_PATHS = {"/api/health"}

# The Google callback arrives from Google's servers, which have no way to hold
# our token. It carries its own HMAC-signed state parameter, which is what
# actually authenticates it — see app/oauth.py.
OPEN_PREFIXES = ("/api/oauth/google/callback",)

_LOCAL_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _configured_token() -> str:
    return (os.environ.get(TOKEN_ENV) or "").strip()


def _is_loopback(request: Request) -> bool:
    client = request.client
    return bool(client and client.host in _LOCAL_HOSTS)


def _presented_token(request: Request) -> str:
    header = request.headers.get(HEADER_NAME)
    if header:
        return header.strip()
    query = request.query_params.get(QUERY_NAME)
    if query:
        return query.strip()
    return (request.cookies.get(COOKIE_NAME) or "").strip()


async def access_gate(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api") or path in OPEN_PATHS or path.startswith(OPEN_PREFIXES):
        return await call_next(request)

    expected = _configured_token()
    if not expected:
        # No token configured: local use only. A tunnelled request arrives from
        # the tunnel agent, which is loopback, so also require that the request
        # wasn't forwarded — that header is what a proxy adds.
        if _is_loopback(request) and "x-forwarded-for" not in request.headers:
            return await call_next(request)
        return JSONResponse(
            status_code=403,
            content={
                "detail": (
                    "This Forge instance is reachable from outside localhost but has no "
                    f"{TOKEN_ENV} set, so it is refusing remote requests. Set one in "
                    "backend/.env and restart."
                )
            },
        )

    # compare_digest so a wrong token can't be recovered by timing the reply.
    if hmac.compare_digest(_presented_token(request), expected):
        response = await call_next(request)
        # Remember it, so a link with ?access_token=… only has to be opened
        # once and the app works normally afterwards.
        if request.query_params.get(QUERY_NAME):
            response.set_cookie(
                COOKIE_NAME,
                expected,
                httponly=True,
                samesite="lax",
                max_age=60 * 60 * 24 * 7,
            )
        return response

    return JSONResponse(
        status_code=401,
        content={"detail": "Missing or invalid access token."},
    )
