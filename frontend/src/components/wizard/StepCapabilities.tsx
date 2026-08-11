import { useEffect, useState } from "react";
import { api } from "../../api";
import type { Agent, CapabilityOption, CapabilityRecommendation } from "../../types";
import type { StepProps } from "./types";

interface Props extends StepProps {
  capabilities: CapabilityOption[];
  agent: Agent | null;
  /** What the agent is for, taken from the Purpose step. Empty if skipped. */
  purpose: string;
}

export function StepCapabilities({ state, update, capabilities, agent, purpose }: Props) {
  const [openKeyPanel, setOpenKeyPanel] = useState<string | null>(null);
  const [tips, setTips] = useState<CapabilityRecommendation[]>([]);
  const [loadingTips, setLoadingTips] = useState(false);
  const [tipsNote, setTipsNote] = useState("");

  // Asked once per purpose, like the model suggestion on the previous step.
  // A failure is silent by design: the full picker below is the real control,
  // and a broken suggestion shouldn't sit in front of it.
  useEffect(() => {
    if (!purpose.trim()) {
      setTips([]);
      return;
    }
    let cancelled = false;
    setLoadingTips(true);
    api
      .recommendCapabilities(purpose)
      .then((r) => {
        if (cancelled) return;
        setTips(r.recommendations);
        setTipsNote(r.unavailable ?? "");
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoadingTips(false);
      });
    return () => {
      cancelled = true;
    };
  }, [purpose]);

  function toggle(key: string) {
    const next = state.capability_keys.includes(key)
      ? state.capability_keys.filter((k) => k !== key)
      : [...state.capability_keys, key];
    update({ capability_keys: next });
  }

  function setCapabilityKey(key: string, value: string) {
    update({ capability_api_keys: { ...state.capability_api_keys, [key]: value } });
  }

  function hasOwnKey(c: CapabilityOption): boolean {
    return Boolean(state.capability_api_keys[c.key]?.trim()) || Boolean(agent?.capability_api_keys_set.includes(c.key));
  }

  function isMissingKey(c: CapabilityOption): boolean {
    return c.requires_api_key && !hasOwnKey(c) && !c.platform_key_available;
  }

  const missingKeys = capabilities.filter((c) => state.capability_keys.includes(c.key) && isMissingKey(c));

  return (
    <div className="wizard-section">
      <p className="field-hint">
        Capabilities are MCP tools your agent can call. Wired ones run for real, in their own
        container. Not-yet-wired capabilities can still be attached now — they're recorded on the
        agent, but won't do anything until this platform's library finishes wiring them up.
      </p>

      {(loadingTips || tips.length > 0 || tipsNote) && (
        <div className="capability-suggestions">
          <div className="capability-suggestions-head">
            <span>Recommended for this agent</span>
            {loadingTips && <span className="field-hint">Reading what this agent is for…</span>}
            {!loadingTips && tipsNote && <span className="field-hint">{tipsNote}</span>}
          </div>
          {tips.length > 0 && (
            <div className="capability-suggestion-chips">
              {tips.map((t) => {
                const on = state.capability_keys.includes(t.key);
                return (
                  <button
                    key={t.key}
                    type="button"
                    className={`capability-chip ${on ? "on" : ""}`}
                    onClick={() => toggle(t.key)}
                    title={on ? "Attached — click to remove" : "Click to attach"}
                  >
                    <span className="capability-chip-icon">{t.icon}</span>
                    <span className="capability-chip-body">
                      <strong>{t.name}</strong>
                      <span>{t.reason}</span>
                    </span>
                    <span className="capability-chip-state">{on ? "✓" : "+"}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
      )}

      {missingKeys.length > 0 && (
        <div className="capability-key-warning">
          ⚠️ {missingKeys.map((c) => c.name).join(", ")} need{missingKeys.length === 1 ? "s" : ""} its
          own API key before this agent can deploy — click the ⚙️ on the card to add it.
        </div>
      )}

      <div className="capability-grid-cols">
        {capabilities.map((c) => {
          const checked = state.capability_keys.includes(c.key);
          const ownKey = hasOwnKey(c);
          const missing = isMissingKey(c);
          return (
            <div key={c.key} className={`capability-card ${checked ? "checked" : ""}`}>
              <div className="capability-card-head">
                <label className="capability-checkbox-row">
                  <input type="checkbox" checked={checked} onChange={() => toggle(c.key)} />
                  <span className="capability-icon">{c.icon}</span>
                  <div>
                    <div className="capability-name">
                      {c.name} {!c.wired && <span className="tag">not wired yet</span>}
                    </div>
                    <div className="capability-desc">{c.description}</div>
                  </div>
                </label>
                {c.requires_api_key && (
                  <button
                    type="button"
                    className={`capability-key-cog ${missing ? "needs-key" : ""}`}
                    title={
                      ownKey
                        ? "Using your own API key — click to edit"
                        : c.platform_key_available
                          ? "Using Forge's shared key — click to add your own"
                          : "This capability needs an API key"
                    }
                    onClick={() => setOpenKeyPanel(openKeyPanel === c.key ? null : c.key)}
                  >
                    ⚙️
                  </button>
                )}
              </div>

              {openKeyPanel === c.key && (
                <div className="capability-key-panel">
                  <label className="field">
                    <span>{c.name} API key</span>
                    <input
                      type="password"
                      autoComplete="off"
                      value={state.capability_api_keys[c.key] ?? ""}
                      onChange={(e) => setCapabilityKey(c.key, e.target.value)}
                      placeholder={
                        agent?.capability_api_keys_set.includes(c.key)
                          ? "•••••••• (unchanged — leave blank to keep)"
                          : "Paste your API key"
                      }
                    />
                  </label>
                  <p className="field-hint">
                    {ownKey
                      ? "This agent uses its own key, not the platform's shared one."
                      : c.platform_key_available
                        ? "Works out of the box using Forge's shared key. Add your own above for a private, higher-limit key."
                        : c.api_key_help}
                  </p>
                  {ownKey && c.api_key_help && <p className="field-hint">{c.api_key_help}</p>}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
