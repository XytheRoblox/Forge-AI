import { useState } from "react";
import { api } from "../api";
import { EndpointList } from "../components/wizard/EndpointList";
import { GoogleConnect } from "../components/wizard/GoogleConnect";
import type { Agent, CapabilityOption, EndpointSpec } from "../types";

interface Props {
  agent: Agent;
  capabilities: CapabilityOption[];
  onBack: () => void;
  /** Re-read the agent list after something changed, without navigating. */
  onAgentUpdated: () => void | Promise<void>;
  onRebuild: (agent: Agent) => void;
  notify: (message: string, kind?: "success" | "error") => void;
}

export function AgentPage({
  agent,
  capabilities,
  onBack,
  onAgentUpdated,
  onRebuild,
  notify,
}: Props) {
  const [restarting, setRestarting] = useState(false);
  const [regenerating, setRegenerating] = useState(false);
  const [themeColor, setThemeColor] = useState(agent.theme_color);
  const [iframeKey, setIframeKey] = useState(0);
  const [editingEndpoints, setEditingEndpoints] = useState<EndpointSpec[] | null>(null);
  const [savingEndpoints, setSavingEndpoints] = useState(false);

  const googleCapabilities = capabilities.filter(
    (c) => c.oauth_provider === "google" && agent.capability_keys.includes(c.key)
  );

  // The connected account is only editable from the wizard's Review step,
  // which a deployed agent never reaches — so reconnecting after changing
  // scopes, or revoking access, was impossible without deleting the agent.
  async function refreshAgent() {
    await onAgentUpdated();
  }

  const webpageUrl = agent.service_url
    ? `${agent.service_url}/`
    : agent.container_port
      ? `http://localhost:${agent.container_port}/`
      : null;

  async function handleRestart() {
    setRestarting(true);
    try {
      await api.restartAgent(agent.id);
      notify(`"${agent.name}" restarted.`);
      // The host port changes on restart, so the record has to be re-read and
      // the iframe remounted, or it keeps pointing at a dead port.
      await onAgentUpdated();
      setIframeKey((k) => k + 1);
    } catch (e) {
      notify((e as Error).message, "error");
    } finally {
      setRestarting(false);
    }
  }

  async function handleRegenerateWebpage() {
    setRegenerating(true);
    try {
      const updated = await api.regenerateWebpage(agent.id);
      setThemeColor(updated.theme_color);
      notify("Webpage regenerated with a new theme.");
      await onAgentUpdated();
      setIframeKey((k) => k + 1);
    } catch (e) {
      notify((e as Error).message, "error");
    } finally {
      setRegenerating(false);
    }
  }

  async function handleThemeChange(color: string) {
    setThemeColor(color);
    try {
      await api.updateTheme(agent.id, color);
      setIframeKey((k) => k + 1);
    } catch (e) {
      notify((e as Error).message, "error");
    }
  }

  async function handleSaveEndpoints() {
    if (!editingEndpoints) return;
    setSavingEndpoints(true);
    try {
      const updated = await api.updateAgent(agent.id, { endpoints: editingEndpoints });
      notify("Endpoints saved — rebuilding to apply changes.");
      setEditingEndpoints(null);
      onRebuild(updated);
    } catch (e) {
      notify((e as Error).message, "error");
    } finally {
      setSavingEndpoints(false);
    }
  }

  return (
    <div className="agent-page">
      <button className="back-link" onClick={onBack}>
        ← Back to agents
      </button>

      <div className="agent-page-header">
        <div>
          <h2>{agent.name}</h2>
          {agent.container_port && (
            <span className="container-info">
              <span className="pulse-dot" /> running in container · port {agent.container_port}
            </span>
          )}
        </div>
        <div className="agent-page-actions">
          <label className="theme-picker">
            Theme
            <input
              type="color"
              value={themeColor}
              onChange={(e) => handleThemeChange(e.target.value)}
            />
          </label>
          <button onClick={handleRegenerateWebpage} disabled={regenerating}>
            {regenerating ? "Regenerating…" : "Regenerate webpage"}
          </button>
          {webpageUrl && (
            <a className="btn-outline-link" href={webpageUrl} target="_blank" rel="noreferrer">
              Open in new tab ↗
            </a>
          )}
          <button onClick={handleRestart} disabled={restarting}>
            {restarting ? "Restarting…" : "Restart agent"}
          </button>
          {/* Restart reuses the existing container, so anything baked in at
              build time — a Google token, a changed capability, a new runtime
              image — needs this instead. Previously the only way to trigger a
              rebuild from here was to save the endpoints form. */}
          <button className="btn-primary" onClick={() => onRebuild(agent)}>
            Redeploy
          </button>
        </div>
      </div>

      {googleCapabilities.length > 0 && (
        <>
          <GoogleConnect
            capabilities={googleCapabilities}
            agent={agent}
            // Already saved — there's no unsaved wizard state to flush here.
            onPersist={async () => agent}
            onChanged={refreshAgent}
            notify={notify}
          />
          <p className="field-hint">
            The connected account is baked in when the agent is built, so use Redeploy after
            connecting or changing scopes — restarting reuses the existing container and keeps
            the old token.
          </p>
        </>
      )}

      <div className="agent-page-body">
        <div className="agent-webpage-frame">
          {webpageUrl ? (
            <iframe
              key={iframeKey}
              src={webpageUrl}
              title={`${agent.name} interactive webpage`}
            />
          ) : (
            <div className="empty-state">No running container.</div>
          )}
        </div>

        <div className="agent-endpoints-panel">
          <h3>API Endpoints</h3>
          <p className="field-hint">
            These are for programmatic access — separate from the interactive webpage above.
          </p>

          {editingEndpoints === null ? (
            <>
              {agent.endpoints.length === 0 ? (
                <div className="empty-state">No custom endpoints configured yet.</div>
              ) : (
                <ul className="endpoint-list">
                  {agent.endpoints.map((ep) => (
                    <li key={ep.id} className="endpoint-item">
                      <div className="endpoint-item-top">
                        <span className="endpoint-method">{ep.method}</span>
                        <span className="endpoint-path">{ep.path}</span>
                      </div>
                      <p className="endpoint-desc">{ep.description}</p>
                      <pre className="option-card-example">
                        {`curl -X ${ep.method} http://localhost:${agent.container_port}${ep.path} \\\n  -H "Content-Type: application/json" \\\n  -d '{...}'`}
                      </pre>
                    </li>
                  ))}
                </ul>
              )}
              <button onClick={() => setEditingEndpoints(agent.endpoints)}>Manage endpoints</button>
            </>
          ) : (
            <>
              <EndpointList endpoints={editingEndpoints} onChange={setEditingEndpoints} />
              <div className="actions">
                <button onClick={() => setEditingEndpoints(null)} disabled={savingEndpoints}>
                  Cancel
                </button>
                <button
                  className="btn-primary"
                  onClick={handleSaveEndpoints}
                  disabled={savingEndpoints}
                >
                  {savingEndpoints ? "Saving…" : "Save & rebuild"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
