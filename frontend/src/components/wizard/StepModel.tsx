import { useEffect, useState } from "react";
import { api } from "../../api";
import type { ModelOption, ModelRecommendation } from "../../types";
import type { StepProps } from "./types";

interface Props extends StepProps {
  models: ModelOption[];
  /** What the agent is for, taken from the Purpose step. Empty if skipped. */
  purpose: string;
}

/** Groups by who built the weights (Llama, DeepSeek, Mistral, Qwen) rather
 * than by who serves them — every model is served by the same provider, so
 * provider groups would be one big undifferentiated list. Insertion order
 * from the API is preserved, so the backend decides how families are ranked. */
function groupByFamily(models: ModelOption[]): Map<string, ModelOption[]> {
  const groups = new Map<string, ModelOption[]>();
  for (const m of models) {
    if (!groups.has(m.family_label)) groups.set(m.family_label, []);
    groups.get(m.family_label)!.push(m);
  }
  return groups;
}

export function StepModel({ state, update, models, purpose }: Props) {
  const groups = groupByFamily(models);
  const [tip, setTip] = useState<ModelRecommendation | null>(null);
  const [loadingTip, setLoadingTip] = useState(false);

  // Asked once per purpose. A failure is silent by design — the suggestion is
  // a convenience, and a broken one shouldn't sit in the way of the picker.
  useEffect(() => {
    if (!purpose) {
      setTip(null);
      return;
    }
    let cancelled = false;
    setLoadingTip(true);
    api
      .recommendModel(purpose)
      .then((r) => {
        if (!cancelled) setTip(r.recommendation);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoadingTip(false);
      });
    return () => {
      cancelled = true;
    };
  }, [purpose]);

  const tipApplied =
    tip !== null && state.model_provider === tip.provider && state.model_id === tip.model_id;

  return (
    <div className="wizard-section">
      {purpose && (loadingTip || tip) && (
        <div className="model-recommendation">
          {loadingTip ? (
            <span className="field-hint">Looking at what this agent is for…</span>
          ) : (
            tip && (
              <>
                <div className="model-recommendation-body">
                  <span className="model-recommendation-label">Recommended</span>
                  <strong>{tip.label}</strong>
                  {tip.reason && <span className="model-recommendation-why">{tip.reason}</span>}
                </div>
                <button
                  type="button"
                  className={tipApplied ? "" : "btn-primary"}
                  disabled={tipApplied}
                  onClick={() =>
                    update({
                      model_provider: tip.provider,
                      model_id: tip.model_id,
                      hosting_mode: "api",
                    })
                  }
                >
                  {tipApplied ? "Selected" : "Use this"}
                </button>
              </>
            )
          )}
        </div>
      )}

      <div className="field">
        <span>Choose a model</span>
        <div className="model-provider-groups">
          {Array.from(groups.entries()).map(([familyLabel, groupModels]) => {
            const hasAvailable = groupModels.some((m) => m.available);
            const containsSelected = groupModels.some(
              (m) => m.provider === state.model_provider && m.model_id === state.model_id
            );
            return (
              <details
                key={familyLabel}
                className="collapsible model-provider-group"
                open={hasAvailable || containsSelected}
              >
                <summary>
                  <span>{familyLabel}</span>
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
                            hosting_mode: "api",
                          })
                        }
                      >
                        <div className="option-card-top">
                          <span className="option-card-title">{m.label}</span>
                          {tip && tip.model_id === m.model_id && (
                            <span className="tag tag-recommended">recommended</span>
                          )}
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
