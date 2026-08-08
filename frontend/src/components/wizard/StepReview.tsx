import type { Agent, CapabilityOption, ModelOption } from "../../types";
import { CronJobList } from "./CronJobList";
import type { StepProps } from "./types";

interface Props extends StepProps {
  models: ModelOption[];
  capabilities: CapabilityOption[];
  agent: Agent | null;
  onSaveDraft: () => void;
  onDeploy: () => void;
  savingDraft: boolean;
  deploying: boolean;
  dockerAvailable: boolean | null;
  error: string | null;
}

export function StepReview({
  state,
  update,
  models,
  capabilities,
  agent,
  onSaveDraft,
  onDeploy,
  savingDraft,
  deploying,
  dockerAvailable,
  error,
}: Props) {
  const model = models.find(
    (m) => m.provider === state.model_provider && m.model_id === state.model_id
  );
  const selectedCapabilities = capabilities.filter((c) => state.capability_keys.includes(c.key));
  const keyedCapabilities = selectedCapabilities.filter((c) => c.requires_api_key);
  const missingModelKey =
    state.hosting_mode === "api" &&
    state.model_provider !== "featherless" &&
    !state.model_api_key.trim() &&
    !agent?.has_model_api_key;
  const missingCapabilityKeys = keyedCapabilities.filter(
    (c) =>
      !(state.capability_api_keys[c.key] ?? "").trim() &&
      !agent?.capability_api_keys_set.includes(c.key) &&
      !c.platform_key_available
  );

  return (
    <div className="wizard-section">
      <div className="review-grid">
        <div className="review-row">
          <span className="review-label">Name</span>
          <span className="review-value">{state.name || "—"}</span>
        </div>
        <div className="review-row">
          <span className="review-label">Model</span>
          <span className="review-value">{model?.label ?? state.model_id}</span>
        </div>
        <div className="review-row">
          <span className="review-label">Hosting</span>
          <span className="review-value">
            {state.hosting_mode === "api" ? "API-hosted (Docker container)" : "Local"}
          </span>
        </div>
        <div className="review-row">
          <span className="review-label">Capabilities</span>
          <span className="review-value">
            {selectedCapabilities.length === 0
              ? "None attached"
              : selectedCapabilities.map((c) => c.name).join(", ")}
          </span>
        </div>
        <div className="review-row">
          <span className="review-label">Custom endpoints</span>
          <span className="review-value">
            {state.endpoints.length === 0
              ? "None configured"
              : state.endpoints.map((e) => `${e.method} ${e.path}`).join(", ")}
          </span>
        </div>
        <div className="review-row">
          <span className="review-label">Scheduled tasks</span>
          <span className="review-value">
            {state.cron_jobs.length === 0 ? "None" : `${state.cron_jobs.length} job(s)`}
          </span>
        </div>
        <div className="review-row">
          <span className="review-label">Webpage theme</span>
          <span className="review-value">
            <input
              type="color"
              value={state.theme_color}
              onChange={(e) => update({ theme_color: e.target.value })}
            />
          </span>
        </div>
      </div>

      <details className="collapsible">
        <summary>Scheduled tasks (optional)</summary>
        <p className="field-hint">
          Each job runs on its own schedule, prompting the agent with an instruction — the result
          gets logged to its memory. Uses standard 5-field cron syntax.
        </p>
        <CronJobList jobs={state.cron_jobs} onChange={(cron_jobs) => update({ cron_jobs })} />
      </details>

      <label className="field">
        <span>System prompt</span>
        <textarea value={state.system_prompt} readOnly rows={8} />
      </label>

      {state.hosting_mode === "api" && state.model_provider !== "featherless" && (
        <label className="field">
          <span>{model?.provider_label ?? "Model provider"} API key</span>
          <input
            type="password"
            autoComplete="off"
            value={state.model_api_key}
            onChange={(e) => update({ model_api_key: e.target.value })}
            placeholder={agent?.has_model_api_key ? "•••••••• (unchanged — leave blank to keep)" : "Paste your API key"}
          />
          <p className="field-hint">
            This agent's own container uses this key to call {model?.provider_label ?? "the model provider"}'s
            API directly — it isn't shared with any other agent.
          </p>
        </label>
      )}

      {!state.system_prompt.trim() && (
        <div className="error">
          No system prompt yet — go back to the Manifesto step to write or generate one before
          deploying.
        </div>
      )}

      {missingModelKey && (
        <div className="error">
          This agent needs a {model?.provider_label ?? "model provider"} API key before it can
          deploy.
        </div>
      )}

      {missingCapabilityKeys.map((c) => (
        <div className="error" key={c.key}>
          The {c.name} capability needs its own API key before this agent can deploy — go back to
          the Capabilities step and click its ⚙️ icon to add one.
        </div>
      ))}

      {dockerAvailable === false && (
        <div className="docker-banner">
          Docker isn't reachable right now, so Deploy will fail until Docker Desktop is running.
          You can still save this as a draft.
        </div>
      )}

      {error && <div className="error">{error}</div>}

      <div className="actions">
        <button
          onClick={onSaveDraft}
          disabled={savingDraft || deploying || !state.name.trim()}
        >
          {savingDraft ? "Saving…" : "Save draft"}
        </button>
        <button
          className="btn-primary"
          onClick={onDeploy}
          disabled={
            savingDraft ||
            deploying ||
            !state.name.trim() ||
            !state.system_prompt.trim() ||
            missingModelKey ||
            missingCapabilityKeys.length > 0
          }
        >
          {deploying ? "Deploying…" : "🚀 Deploy"}
        </button>
      </div>
    </div>
  );
}
