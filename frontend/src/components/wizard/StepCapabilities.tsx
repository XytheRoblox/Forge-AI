import { useState } from "react";
import type { Agent, CapabilityOption } from "../../types";
import type { StepProps } from "./types";

interface Props extends StepProps {
  capabilities: CapabilityOption[];
  agent: Agent | null;
}

export function StepCapabilities({ state, update, capabilities, agent }: Props) {
  const [openKeyPanel, setOpenKeyPanel] = useState<string | null>(null);

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
