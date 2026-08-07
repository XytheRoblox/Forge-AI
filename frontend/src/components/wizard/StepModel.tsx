import type { ModelOption } from "../../types";
import type { StepProps } from "./types";

interface Props extends StepProps {
  models: ModelOption[];
}

function groupByProvider(models: ModelOption[]): Map<string, ModelOption[]> {
  const groups = new Map<string, ModelOption[]>();
  for (const m of models) {
    if (!groups.has(m.provider_label)) groups.set(m.provider_label, []);
    groups.get(m.provider_label)!.push(m);
  }
  return groups;
}

export function StepModel({ state, update, models }: Props) {
  const groups = groupByProvider(models);

  return (
    <div className="wizard-section">
      <label className="field">
        <span>Agent name</span>
        <input
          value={state.name}
          onChange={(e) => update({ name: e.target.value })}
          placeholder="Trip Concierge"
          autoFocus
        />
        <span className="field-hint">
          This is just a label for your own reference — it doesn't affect how the agent behaves.
        </span>
      </label>

      <div className="field">
        <span>Choose a model</span>
        <div className="model-provider-groups">
          {Array.from(groups.entries()).map(([providerLabel, groupModels]) => {
            const hasAvailable = groupModels.some((m) => m.available);
            const containsSelected = groupModels.some(
              (m) => m.provider === state.model_provider && m.model_id === state.model_id
            );
            return (
              <details
                key={providerLabel}
                className="collapsible model-provider-group"
                open={hasAvailable || containsSelected}
              >
                <summary>
                  <span>{providerLabel}</span>
                  <span className="model-count-badge">{groupModels.length}</span>
                </summary>
                <div className="option-card-grid">
                  {groupModels.map((m) => {
                    const selected =
                      state.model_provider === m.provider && state.model_id === m.model_id;
                    return (
                      <button
                        key={`${m.provider}::${m.model_id}`}
                        type="button"
                        className={`option-card ${selected ? "selected" : ""} ${!m.available ? "disabled" : ""}`}
                        disabled={!m.available}
                        onClick={() =>
                          update({
                            model_provider: m.provider,
                            model_id: m.model_id,
                            hosting_mode: m.provider === "ollama" ? "local" : "api",
                          })
                        }
                      >
                        <div className="option-card-top">
                          <span className="option-card-title">{m.label}</span>
                        </div>
                        <p className="option-card-desc">{m.description}</p>
                      </button>
                    );
                  })}
                </div>
              </details>
            );
          })}
        </div>
      </div>
    </div>
  );
}
