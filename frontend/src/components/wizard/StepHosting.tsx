import type { StepProps } from "./types";

const OPTIONS = [
  {
    value: "api",
    title: "API-hosted",
    available: true,
    description:
      "Your agent runs as its own Docker container on this machine. When deployed, it calls your chosen model's API over the network for every reply.",
    details: [
      "Spins up a dedicated container per agent",
      "Needs an API key for the model provider you picked",
      "Stop it any time from the chat page — the container is removed",
    ],
  },
  {
    value: "local",
    title: "Local model",
    available: false,
    description:
      "Run inference entirely on your own hardware, with no API key and no data leaving your machine. Not wired up yet — every model in the catalog is currently API-hosted.",
    details: [
      "No external network calls for inference",
      "First deploy downloads the model file (multi-GB) — later deploys reuse it",
      "No tool use (capabilities) yet, and generally less capable than the hosted models",
    ],
  },
];

export function StepHosting({ state, update }: StepProps) {
  return (
    <div className="wizard-section">
      <div className="option-card-grid stacked">
        {OPTIONS.map((opt) => (
          <button
            key={opt.value}
            type="button"
            className={`option-card ${state.hosting_mode === opt.value ? "selected" : ""} ${
              !opt.available ? "disabled" : ""
            }`}
            disabled={!opt.available}
            onClick={() => update({ hosting_mode: opt.value })}
          >
            <div className="option-card-top">
              <span className="option-card-title">{opt.title}</span>
              {!opt.available && <span className="tag">coming soon</span>}
            </div>
            <p className="option-card-desc">{opt.description}</p>
            <ul className="option-card-details">
              {opt.details.map((d) => (
                <li key={d}>{d}</li>
              ))}
            </ul>
          </button>
        ))}
      </div>
    </div>
  );
}
