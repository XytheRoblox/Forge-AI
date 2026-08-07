import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import type { BuildJob } from "../types";

interface Props {
  agentId: number;
  jobId: string;
  onSuccess: () => void;
  onBack: () => void;
}

function StepIcon({ status }: { status: string }) {
  if (status === "success") return <span className="step-icon step-icon-success">✓</span>;
  if (status === "failed") return <span className="step-icon step-icon-failed">✗</span>;
  if (status === "running") return <span className="step-icon step-icon-running" />;
  return <span className="step-icon step-icon-pending" />;
}

export function BuildingPage({ agentId, jobId, onSuccess, onBack }: Props) {
  const [job, setJob] = useState<BuildJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const status = await api.getBuildStatus(agentId, jobId);
        if (cancelled) return;
        setJob(status);
        if (status.status === "running") {
          timerRef.current = setTimeout(poll, 800);
        } else if (status.status === "success") {
          setTimeout(onSuccess, 600);
        }
      } catch (e) {
        if (!cancelled) setError((e as Error).message);
      }
    }

    poll();
    return () => {
      cancelled = true;
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [agentId, jobId, onSuccess]);

  const failedStep = job?.steps.find((s) => s.status === "failed");

  return (
    <div className="building-page">
      <h1>Building your agent…</h1>
      <p className="wizard-subtitle">
        Validating your configuration, writing its files, and starting its container.
      </p>

      {error && <div className="error">{error}</div>}

      {job && (
        <>
          <ul className="build-steps">
            {job.steps.map((step) => (
              <li key={step.name} className={`build-step build-step-${step.status}`}>
                <StepIcon status={step.status} />
                <div>
                  <div className="build-step-name">{step.name}</div>
                  {step.detail && <div className="build-step-detail">{step.detail}</div>}
                </div>
              </li>
            ))}
          </ul>

          <details className="collapsible build-status-dropdown" open={job.status === "running"}>
            <summary>Detailed build status</summary>
            <ul className="build-status-log">
              {job.steps.map((step) => (
                <li key={step.name}>
                  <span className={`build-status-log-tag build-status-log-tag-${step.status}`}>
                    {step.status}
                  </span>
                  <span className="build-status-log-name">{step.name}</span>
                  {step.detail && <span className="build-status-log-detail">— {step.detail}</span>}
                </li>
              ))}
            </ul>
          </details>
        </>
      )}

      {job?.status === "failed" && (
        <div className="build-failed">
          <div className="error">
            Build failed at "{failedStep?.name}": {failedStep?.detail}
          </div>
          <button className="btn-primary" onClick={onBack}>
            Back to configuration
          </button>
        </div>
      )}
    </div>
  );
}
