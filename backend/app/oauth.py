"""Google OAuth for agents that reach a real Google account.

This is the *owner-connected* model: whoever builds the agent authorises their
own Google account, and the agent acts as them. That's deliberately not the
same thing as every visitor connecting their own account — that would need an
end-user identity concept the platform doesn't have, and would make each agent
container multi-tenant.

Nothing here is required for Forge to run. With no client configured every
entry point reports "not configured" and the wizard says so, rather than
offering a button that leads to a Google error page.
"""

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional
from urllib.parse import urlencode

import httpx

AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v3/userinfo"
REVOKE_ENDPOINT = "https://oauth2.googleapis.com/revoke"

# Always requested alongside whatever the capabilities need, so the connected
# account can be named back to the user ("Connected as ada@example.com").
IDENTITY_SCOPES = ["openid", "email"]

# A state token is only valid briefly — it exists to tie a callback back to the
# agent that started the flow and to stop a stray callback binding a token to
# someone else's agent.
STATE_TTL_SECONDS = 600


def client_id() -> Optional[str]:
    return os.environ.get("GOOGLE_CLIENT_ID") or None


def _client_secret() -> Optional[str]:
    return os.environ.get("GOOGLE_CLIENT_SECRET") or None


def redirect_uri() -> str:
    """Must match a redirect URI registered on the OAuth client exactly."""
    base = os.environ.get("PUBLIC_BACKEND_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/api/oauth/google/callback"


def is_configured() -> bool:
    return bool(client_id() and _client_secret())


def _signing_key() -> bytes:
    # Falls back to the client secret so state is still signed on a default
    # install; a dedicated secret is better and is what .env.example suggests.
    return (os.environ.get("OAUTH_STATE_SECRET") or _client_secret() or "forge-dev").encode()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def make_state(agent_id: int) -> str:
    """Signed, expiring state. Carries the agent id so the callback knows
    which agent to attach the grant to without trusting the query string."""
    payload = _b64(json.dumps({"agent_id": agent_id, "ts": int(time.time())}).encode())
    signature = _b64(hmac.new(_signing_key(), payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{signature}"


def read_state(state: str) -> Optional[int]:
    """The agent id from a state token, or None if it's forged or stale."""
    try:
        payload, signature = state.split(".", 1)
    except ValueError:
        return None
    expected = _b64(hmac.new(_signing_key(), payload.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        return None
    try:
        data = json.loads(_unb64(payload))
    except (ValueError, json.JSONDecodeError):
        return None
    if int(time.time()) - int(data.get("ts", 0)) > STATE_TTL_SECONDS:
        return None
    agent_id = data.get("agent_id")
    return int(agent_id) if isinstance(agent_id, int) else None


def authorization_url(agent_id: int, scopes: list[str]) -> str:
    requested = list(dict.fromkeys([*IDENTITY_SCOPES, *scopes]))
    params = {
        "client_id": client_id(),
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": " ".join(requested),
        "state": make_state(agent_id),
        # offline + consent is what actually yields a refresh token. Without
        # prompt=consent Google omits it on repeat authorisations, and the
        # grant silently stops surviving the first hour.
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{AUTH_ENDPOINT}?{urlencode(params)}"


def exchange_code(code: str) -> dict:
    """Trade an authorisation code for tokens. Raises RuntimeError on failure."""
    response = httpx.post(
        TOKEN_ENDPOINT,
        data={
            "code": code,
            "client_id": client_id(),
            "client_secret": _client_secret(),
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        },
        timeout=30.0,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Google rejected the authorisation: {response.text[:200]}")
    return response.json()


def refresh_access_token(refresh_token: str) -> str:
    """A fresh access token. Access tokens last about an hour, so this runs
    per use rather than being cached anywhere long-lived."""
    response = httpx.post(
        TOKEN_ENDPOINT,
        data={
            "refresh_token": refresh_token,
            "client_id": client_id(),
            "client_secret": _client_secret(),
            "grant_type": "refresh_token",
        },
        timeout=30.0,
    )
    if response.status_code != 200:
        raise RuntimeError(
            "Google refused to refresh this connection — it may have been revoked. "
            "Reconnect the account."
        )
    return response.json()["access_token"]


def account_email(access_token: str) -> Optional[str]:
    """Best effort: used only to show which account is connected."""
    try:
        response = httpx.get(
            USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15.0,
        )
        if response.status_code == 200:
            return response.json().get("email")
    except httpx.HTTPError:
        pass
    return None


def revoke(refresh_token: str) -> None:
    """Best effort — a token Google has already forgotten still needs to be
    dropped locally, so failure here is not an error."""
    try:
        httpx.post(REVOKE_ENDPOINT, data={"token": refresh_token}, timeout=15.0)
    except httpx.HTTPError:
        pass
