import { useState } from "react";
import { api } from "../../api";
import type { Agent, CapabilityOption, ModelOption } from "../../types";
import { StepCapabilities } from "./StepCapabilities";
import { StepEndpoint } from "./StepEndpoint";
import { StepHosting } from "./StepHosting";
import { StepManifesto } from "./StepManifesto";
import { StepModel } from "./StepModel";
import { StepReview } from "./StepReview";
import type { WizardState } from "./types";
import { WizardShell } from "./WizardShell";

interface Props {
  agent: Agent | null;
  models: ModelOption[];
  capabilities: CapabilityOption[];
  dockerAvailable: boolean | null;
  onCancel: () => void;
  onSaved: (agent: Agent) => void;
  onBuildStarted: (agentId: number, jobId: string) => void;
  notify: (message: string, kind?: "success" | "error") => void;
}

const STEPS = [
  { key: "model", label: "Model" },
  { key: "hosting", label: "Hosting" },
  { key: "capabilities", label: "Capabilities" },
  { key: "manifesto", label: "Manifesto" },
  { key: "endpoint", label: "Endpoints" },
  { key: "review", label: "Review & Deploy" },
];

function initialState(agent: Agent | null, models: ModelOption[]): WizardState {
  // Default to whatever the catalog actually offers first, rather than a
  // hardcoded id — models come and go, and a stale default silently produces
  // an agent pinned to a model that no longer exists.
  const fallback = models.find((m) => m.available);
  return {
    name: agent?.name ?? "",
    model_provider: agent?.model_provider ?? fallback?.provider ?? "featherless",
    model_id: agent?.model_id ?? fallback?.model_id ?? "",
    hosting_mode: agent?.hosting_mode ?? "api",
    model_api_key: "",
    capability_keys: agent?.capability_keys ?? [],
    capability_api_keys: {},
    endpoints: agent?.endpoints ?? [],
    cron_jobs: agent?.cron_jobs ?? [],
    theme_color: agent?.theme_color ?? "#aa3bff",
    manifesto: agent?.manifesto ?? "",
    system_prompt: agent?.system_prompt ?? "",
  };
}

export function Wizard({
  agent,
  models,
  capabilities,
  dockerAvailable,
  onCancel,
  onSaved,
  onBuildStarted,
  notify,
}: Props) {
  const [stepIndex, setStepIndex] = useState(0);
  const [state, setState] = useState<WizardState>(() => initialState(agent, models));
  const [autoCreated, setAutoCreated] = useState<Agent | null>(null);
  const [expanding, setExpanding] = useState(false);
  const [savingDraft, setSavingDraft] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function update(patch: Partial<WizardState>) {
    setState((prev) => ({ ...prev, ...patch }));
  }

  // Creates or updates the underlying agent record without navigating away —
  // used to get a real agent id before calling expand-manifesto, and again
  // for the final save/deploy.
  async function ensurePersisted(): Promise<Agent> {
    const target = agent ?? autoCreated;
    const saved = target
      ? await api.updateAgent(target.id, state)
      : await api.createAgent(state);
    if (!agent) setAutoCreated(saved);
    return saved;
  }

  async function handleExpand() {
    if (!state.manifesto.trim()) return;
    setExpanding(true);
    setError(null);
    try {
      const current = await ensurePersisted();
      const { system_prompt } = await api.expandManifesto(current.id, state.manifesto);
      update({ system_prompt });
      notify("System prompt generated from your manifesto.");
    } catch (e) {
      const message = (e as Error).message;
      setError(message);
      notify(message, "error");
    } finally {
      setExpanding(false);
    }
  }

  async function handleSaveDraft() {
    setSavingDraft(true);
    setError(null);
    try {
      const saved = await ensurePersisted();
      notify(`"${saved.name}" saved as a draft.`);
      onSaved(saved);
    } catch (e) {
      const message = (e as Error).message;
      setError(message);
      notify(message, "error");
    } finally {
      setSavingDraft(false);
    }
  }

  async function handleDeploy() {
    setDeploying(true);
    setError(null);
    try {
      const saved = await ensurePersisted();
      const { job_id } = await api.startBuild(saved.id);
      onBuildStarted(saved.id, job_id);
    } catch (e) {
      const message = (e as Error).message;
      setError(message);
      notify(message, "error");
      setDeploying(false);
    }
  }

  const canGoNext = stepIndex !== 0 || state.name.trim().length > 0;
  const isReview = stepIndex === STEPS.length - 1;

  function goNext() {
    if (!canGoNext) return;
    setError(null);
    setStepIndex((i) => Math.min(i + 1, STEPS.length - 1));
  }

  function goPrev() {
    if (stepIndex === 0) {
      onCancel();
    } else {
      setError(null);
      setStepIndex((i) => Math.max(i - 1, 0));
    }
  }

  let stepContent;
  switch (STEPS[stepIndex].key) {
    case "model":
      stepContent = <StepModel state={state} update={update} models={models} />;
      break;
    case "hosting":
      stepContent = <StepHosting state={state} update={update} />;
      break;
    case "capabilities":
      stepContent = (
        <StepCapabilities
          state={state}
          update={update}
          capabilities={capabilities}
          agent={agent ?? autoCreated}
        />
      );
      break;
    case "manifesto":
      stepContent = (
        <StepManifesto state={state} update={update} onExpand={handleExpand} expanding={expanding} />
      );
      break;
    case "endpoint":
      stepContent = <StepEndpoint state={state} update={update} />;
      break;
    case "review":
      stepContent = (
        <StepReview
          state={state}
          update={update}
          models={models}
          capabilities={capabilities}
          agent={agent ?? autoCreated}
          onSaveDraft={handleSaveDraft}
          onDeploy={handleDeploy}
          savingDraft={savingDraft}
          deploying={deploying}
          dockerAvailable={dockerAvailable}
          error={error}
        />
      );
      break;
  }

  const subtitles: Record<string, string> = {
    model: "Give your agent a name and pick the model that powers it.",
    hosting: "Choose where this agent actually runs.",
    capabilities: "Attach the tools this agent is allowed to use.",
    manifesto: "Tell the agent what it's for — in your words, or the model's.",
    endpoint: "Optionally add API endpoints for developers integrating this agent into their own code.",
    review: "Double-check everything, then save it or take it live.",
  };

  return (
    <WizardShell
      steps={STEPS}
      stepIndex={stepIndex}
      onJump={setStepIndex}
      title={STEPS[stepIndex].label}
      subtitle={subtitles[STEPS[stepIndex].key]}
      footer={
        <>
          {error && !isReview && <div className="error">{error}</div>}
          <div className="wizard-nav">
            <button onClick={goPrev}>{stepIndex === 0 ? "Cancel" : "← Previous"}</button>
            {!isReview && (
              <button className="btn-primary" onClick={goNext} disabled={!canGoNext}>
                Next →
              </button>
            )}
          </div>
        </>
      }
    >
      {stepContent}
    </WizardShell>
  );
}
