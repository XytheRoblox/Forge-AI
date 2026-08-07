import type { ReactNode } from "react";

export interface WizardStepMeta {
  key: string;
  label: string;
}

interface Props {
  steps: WizardStepMeta[];
  stepIndex: number;
  onJump: (index: number) => void;
  title: string;
  subtitle: string;
  children: ReactNode;
  footer: ReactNode;
}

export function WizardShell({ steps, stepIndex, onJump, title, subtitle, children, footer }: Props) {
  return (
    <div className="wizard">
      <ol className="wizard-progress">
        {steps.map((step, i) => (
          <li
            key={step.key}
            className={
              i === stepIndex ? "current" : i < stepIndex ? "done" : ""
            }
            onClick={() => i < stepIndex && onJump(i)}
          >
            <span className="wizard-progress-dot">{i < stepIndex ? "✓" : i + 1}</span>
            <span className="wizard-progress-label">{step.label}</span>
          </li>
        ))}
      </ol>

      <div className="wizard-page">
        <div className="wizard-page-header">
          <span className="wizard-step-count">
            Step {stepIndex + 1} of {steps.length}
          </span>
          <h2>{title}</h2>
          <p className="wizard-subtitle">{subtitle}</p>
        </div>

        <div className="wizard-page-body">{children}</div>

        <div className="wizard-page-footer">{footer}</div>
      </div>
    </div>
  );
}
