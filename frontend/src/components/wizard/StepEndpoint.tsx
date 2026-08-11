import { EndpointList } from "./EndpointList";
import type { StepProps } from "./types";

export function StepEndpoint({ state, update }: StepProps) {
  return (
    <div className="wizard-section">
      <div className="option-card static">
        <div className="option-card-top">
          <span className="option-card-title">Chat &amp; interactive webpage — always included</span>
        </div>
        <p className="option-card-desc">
          Every agent automatically gets a chat endpoint and its own interactive webpage the
          moment it's deployed — generated to match what this agent is for (e.g. an image upload
          field for a tutor agent). Nothing to configure here.
        </p>
      </div>

      <div className="field">
        <span>API endpoints (optional)</span>
        <span className="field-hint">
          For developers who want to integrate this agent into their own code, separate from the
          chat webpage above. Each endpoint maps structured JSON input to an instruction the model
          follows to produce a response. Build the input schema visually, or paste/upload an
          OpenAPI/Swagger JSON document to import one or more operations at once.
        </span>
        <EndpointList
          endpoints={state.endpoints}
          onChange={(endpoints) => update({ endpoints })}
          agentName={state.name}
          purpose={state.manifesto || state.system_prompt}
          capabilityKeys={state.capability_keys}
        />
      </div>
    </div>
  );
}
