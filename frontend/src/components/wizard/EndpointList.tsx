import { useState } from "react";
import type { EndpointSpec } from "../../types";
import { EndpointForm } from "./EndpointForm";
import { EndpointTemplates } from "./EndpointTemplates";

interface Props {
  endpoints: EndpointSpec[];
  onChange: (endpoints: EndpointSpec[]) => void;
  /** Context for the tailored suggestions. Omitted on screens that don't
   * know what the agent is for; the stock templates still show. */
  agentName?: string;
  purpose?: string;
  capabilityKeys?: string[];
}

export function EndpointList({
  endpoints,
  onChange,
  agentName,
  purpose,
  capabilityKeys,
}: Props) {
  const [adding, setAdding] = useState(false);

  function handleAdd(newEndpoints: EndpointSpec[]) {
    onChange([...endpoints, ...newEndpoints]);
    setAdding(false);
  }

  function handleRemove(id: string) {
    onChange(endpoints.filter((e) => e.id !== id));
  }

  return (
    <div className="endpoint-editor">
      <EndpointTemplates
        existing={endpoints}
        onAdd={(ep) => onChange([...endpoints, ep])}
        agentName={agentName}
        purpose={purpose}
        capabilityKeys={capabilityKeys}
      />

      {endpoints.length > 0 && (
        <ul className="endpoint-list">
          {endpoints.map((ep) => (
            <li key={ep.id} className="endpoint-item">
              <div className="endpoint-item-top">
                <span className="endpoint-method">{ep.method}</span>
                <span className="endpoint-path">{ep.path}</span>
                <button className="btn-icon" onClick={() => handleRemove(ep.id)} title="Remove">
                  ×
                </button>
              </div>
              {ep.description && <p className="endpoint-desc">{ep.description}</p>}
            </li>
          ))}
        </ul>
      )}

      {adding ? (
        <EndpointForm onAdd={handleAdd} onCancel={() => setAdding(false)} />
      ) : (
        <button onClick={() => setAdding(true)}>+ Add endpoint</button>
      )}
    </div>
  );
}
