import html

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlmodel import Session

from app import oauth
from app.db import get_session
from app.models import Agent
from app.registry import CAPABILITY_OPTIONS

router = APIRouter(prefix="/api/oauth", tags=["oauth"])

_CAPABILITIES = {c.key: c for c in CAPABILITY_OPTIONS}


def _scopes_for(agent: Agent, provider: str) -> list[str]:
    """Every scope this agent's attached capabilities need from one provider.

    Asked for in a single consent screen: a user who attached Calendar and
    Sheets should authorise once, not once per capability."""
    scopes: list[str] = []
    for key in agent.capability_keys:
        capability = _CAPABILITIES.get(key)
        if capability and capability.oauth_provider == provider:
            scopes.extend(capability.oauth_scopes)
    return list(dict.fromkeys(scopes))


def _close_popup(message: str, ok: bool) -> HTMLResponse:
    """The callback lands in a popup the wizard opened. Tell the opener what
    happened and close, so the user never has to read a bare JSON response or
    find their way back to the wizard by hand."""
    safe = html.escape(message)
    tone = "#1f7a45" if ok else "#a3262b"
    return HTMLResponse(
        f"""<!doctype html>
<meta charset="utf-8">
<title>{'Connected' if ok else 'Connection failed'}</title>
<body style="font-family: system-ui, sans-serif; padding: 40px; text-align: center; color: {tone}">
  <p style="font-size: 15px">{safe}</p>
  <p style="color: #6b747e; font-size: 13px">You can close this window.</p>
  <script>
    try {{
      window.opener && window.opener.postMessage(
        {{ source: "forge-oauth", provider: "google", ok: {str(ok).lower()} }}, "*"
      );
    }} catch (e) {{}}
    setTimeout(() => window.close(), {1200 if ok else 4000});
  </script>
</body>"""
    )


@router.get("/google/status")
def google_status():
    """Whether the platform can offer Google connections at all."""
    return {
        "configured": oauth.is_configured(),
        "redirect_uri": oauth.redirect_uri(),
    }


@router.post("/google/start/{agent_id}")
def google_start(agent_id: int, session: Session = Depends(get_session)):
    if not oauth.is_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Google connections aren't configured on this platform. Add GOOGLE_CLIENT_ID "
                "and GOOGLE_CLIENT_SECRET to backend/.env."
            ),
        )
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    scopes = _scopes_for(agent, "google")
    if not scopes:
        raise HTTPException(
            status_code=400,
            detail="This agent has no capabilities that use a Google account.",
        )
    return {"authorization_url": oauth.authorization_url(agent.id, scopes)}


@router.get("/google/callback")
def google_callback(
    state: str = "",
    code: str = "",
    error: str = "",
    session: Session = Depends(get_session),
):
    if error:
        return _close_popup(f"Google returned an error: {error}", ok=False)
    agent_id = oauth.read_state(state)
    if agent_id is None:
        # Covers a forged state, a tampered one, and simply leaving the consent
        # screen open too long — all of which should fail closed.
        return _close_popup("That authorisation link expired. Try connecting again.", ok=False)
    agent = session.get(Agent, agent_id)
    if agent is None:
        return _close_popup("That agent no longer exists.", ok=False)

    try:
        tokens = oauth.exchange_code(code)
    except RuntimeError as exc:
        return _close_popup(str(exc), ok=False)

    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        # Without a refresh token the connection dies in an hour, so treat it
        # as a failure rather than storing something that quietly stops working.
        return _close_popup(
            "Google didn't return a refresh token. Remove Forge from your Google "
            "account's third-party access list and connect again.",
            ok=False,
        )

    email = oauth.account_email(tokens.get("access_token", ""))
    grants = dict(agent.oauth_grants or {})
    grants["google"] = {
        "refresh_token": refresh_token,
        "scopes": (tokens.get("scope") or "").split(),
        "account": email,
    }
    agent.oauth_grants = grants
    session.add(agent)
    session.commit()
    return _close_popup(f"Connected{' as ' + email if email else ''}.", ok=True)


@router.delete("/google/{agent_id}")
def google_disconnect(agent_id: int, session: Session = Depends(get_session)):
    agent = session.get(Agent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    grants = dict(agent.oauth_grants or {})
    grant = grants.pop("google", None)
    if grant and grant.get("refresh_token"):
        oauth.revoke(grant["refresh_token"])
    agent.oauth_grants = grants
    session.add(agent)
    session.commit()
    return {"connected": False}
