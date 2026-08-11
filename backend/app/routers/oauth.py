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
    find their way back to the wizard by hand.

    Styled rather than left as raw text: this is the last screen in the
    connect flow, it appears immediately after Google's own polished consent
    page, and an unstyled white slab reads like something broke — especially
    on a dark desktop, where a default page is a white flash."""
    safe = html.escape(message)
    accent = "#2f9e5f" if ok else "#d2504a"
    heading = "Connected" if ok else "Couldn't connect"
    return HTMLResponse(
        f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{heading}</title>
<style>
  :root {{
    --bg: #f4f5f7;
    --card: #ffffff;
    --text: #5b6570;
    --heading: #14181d;
    --border: #e3e6ea;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg: #14171b;
      --card: #1b1f25;
      --text: #99a3ad;
      --heading: #eef2f6;
      --border: #2b3138;
    }}
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 24px;
    background: var(--bg);
    color: var(--text);
    font-family: ui-sans-serif, system-ui, "Segoe UI", Roboto, sans-serif;
  }}
  .card {{
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 32px 28px;
    max-width: 380px;
    width: 100%;
    text-align: center;
  }}
  .mark {{
    width: 44px;
    height: 44px;
    margin: 0 auto 18px;
    border-radius: 12px;
    background: {accent};
    color: #fff;
    font-size: 22px;
    line-height: 44px;
    font-weight: 700;
  }}
  h1 {{
    margin: 0 0 8px;
    font-size: 19px;
    letter-spacing: -0.01em;
    color: var(--heading);
  }}
  p {{ margin: 0; font-size: 14px; line-height: 1.5; }}
  .hint {{ margin-top: 14px; font-size: 12.5px; opacity: 0.75; }}
</style>
</head>
<body>
  <div class="card">
    <div class="mark">{'&#10003;' if ok else '!'}</div>
    <h1>{heading}</h1>
    <p>{safe}</p>
    <p class="hint">This window closes itself.</p>
  </div>
  <script>
    try {{
      window.opener && window.opener.postMessage(
        {{ source: "forge-oauth", provider: "google", ok: {str(ok).lower()} }}, "*"
      );
    }} catch (e) {{}}
    setTimeout(() => window.close(), {1400 if ok else 6000});
  </script>
</body>
</html>"""
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
