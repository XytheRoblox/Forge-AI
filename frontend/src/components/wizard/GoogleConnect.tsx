import { useCallback, useEffect, useState } from "react";
import { api } from "../../api";
import type { Agent, CapabilityOption } from "../../types";

interface Props {
  /** The Google-backed capabilities this agent has attached. */
  capabilities: CapabilityOption[];
  agent: Agent | null;
  /**
   * Saves the wizard's current state and returns the stored agent. Consent
   * has to be requested against what the user has actually selected, and the
   * capability list lives in unsaved wizard state until something persists
   * it — so this runs first, or Google is asked for the scopes of whatever
   * was last written, which is usually nothing.
   */
  onPersist: () => Promise<Agent>;
  onChanged: () => void;
  notify: (message: string, kind?: "success" | "error") => void;
}

/**
 * Asks the user to authorise a real Google account for the capabilities that
 * need one. Shown on Review because that's the last point before deploy — the
 * agent can be built and edited without a connection, but it can't do anything
 * useful with Calendar or Sheets until one exists.
 *
 * Consent opens in a popup rather than navigating away, so a half-filled
 * wizard isn't lost to an OAuth round trip. The popup posts back when it's
 * done; the timer is the fallback for a user who closes it manually.
 */
export function GoogleConnect({ capabilities, agent, onPersist, onChanged, notify }: Props) {
  const [configured, setConfigured] = useState<boolean | null>(null);
  const [connecting, setConnecting] = useState(false);

  const connectedAs = agent?.connected_accounts?.google;

  useEffect(() => {
    let cancelled = false;
    api
      .googleOAuthStatus()
      .then((s) => {
        if (!cancelled) setConfigured(s.configured);
      })
      .catch(() => {
        if (!cancelled) setConfigured(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const connect = useCallback(async () => {
    // The window MUST be opened synchronously, in the click itself. A browser
    // only honours window.open while the user gesture is still on the stack,
    // and this handler has async work to do first (saving the agent, then
    // asking the backend for a consent URL) — opening afterwards is silently
    // blocked, which looks exactly like the button doing nothing. So take the
    // window now and point it at the URL once we have one.
    const popup = window.open("", "forge-google-oauth", "width=520,height=680");
    if (!popup) {
      notify("Allow pop-ups for this site to connect a Google account.", "error");
      return;
    }
    popup.document.write(
      "<p style='font-family:system-ui,sans-serif;padding:32px;text-align:center;color:#666'>" +
        "Taking you to Google…</p>"
    );

    setConnecting(true);
    try {
      // Persist first: the agent may not exist yet, and even if it does its
      // stored capability list predates the selection being consented to.
      const saved = await onPersist();
      const { authorization_url } = await api.startGoogleOAuth(saved.id);
      popup.location.href = authorization_url;
      const finish = () => {
        window.removeEventListener("message", onMessage);
        clearInterval(poll);
        setConnecting(false);
        onChanged();
      };
      function onMessage(event: MessageEvent) {
        if (event.data?.source !== "forge-oauth") return;
        if (event.data.ok) notify("Google account connected.");
        finish();
      }
      window.addEventListener("message", onMessage);
      // Covers the user closing the popup without finishing, which sends no
      // message at all.
      const poll = setInterval(() => {
        if (popup.closed) finish();
      }, 700);
    } catch (e) {
      // Don't strand a blank window the user has to close themselves.
      popup.close();
      notify((e as Error).message, "error");
      setConnecting(false);
    }
  }, [onPersist, notify, onChanged]);

  async function disconnect() {
    if (!agent) return;
    try {
      await api.disconnectGoogle(agent.id);
      notify("Google account disconnected.");
      onChanged();
    } catch (e) {
      notify((e as Error).message, "error");
    }
  }

  if (capabilities.length === 0) return null;

  const names = capabilities.map((c) => c.name).join(", ");

  return (
    <div className={`google-connect ${connectedAs ? "connected" : ""}`}>
      <div className="google-connect-body">
        <span className="google-connect-title">
          {connectedAs ? "Google account connected" : "Connect a Google account"}
        </span>
        <span className="field-hint">
          {connectedAs ? (
            <>
              Acting as <strong>{connectedAs}</strong> for {names}.
            </>
          ) : (
            <>
              {names} {capabilities.length === 1 ? "needs" : "need"} access to a real Google
              account. The agent will act as whoever authorises here.
            </>
          )}
        </span>
        {configured === false && (
          <span className="field-hint error-hint">
            Google connections aren't configured on this platform yet — add GOOGLE_CLIENT_ID and
            GOOGLE_CLIENT_SECRET to backend/.env.
          </span>
        )}
      </div>
      {connectedAs ? (
        <button type="button" onClick={disconnect}>
          Disconnect
        </button>
      ) : (
        <button
          type="button"
          className="btn-primary"
          onClick={connect}
          disabled={connecting || configured !== true}
        >
          {connecting ? "Waiting for Google…" : "Authorize with Google"}
        </button>
      )}
    </div>
  );
}
