import type { StepProps } from "./types";

interface Props extends StepProps {
  onExpand: () => void;
  expanding: boolean;
}

export function StepManifesto({ state, update, onExpand, expanding }: Props) {
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
          A label for your own reference — it doesn't affect how the agent behaves.
        </span>
      </label>

      <label className="field">
        <span>Manifesto</span>
        <span className="field-hint">
          Describe what this agent should do in a sentence or two. An LLM call turns this into a
          full system prompt below — you can edit the result, or skip this and write the system
          prompt yourself.
        </span>
        <textarea
          value={state.manifesto}
          onChange={(e) => update({ manifesto: e.target.value })}
          placeholder="What should this agent do?"
          rows={3}
        />
        <button onClick={onExpand} disabled={expanding || !state.manifesto.trim()}>
          {expanding ? "Expanding…" : "✦ Expand into system prompt"}
        </button>
      </label>

      <label className="field">
        <span>System prompt</span>
        <span className="field-hint">
          This is what actually gets sent to the model as its instructions.
        </span>
        <textarea
          value={state.system_prompt}
          onChange={(e) => update({ system_prompt: e.target.value })}
          rows={10}
        />
      </label>
    </div>
  );
}
