import { useState } from "react";
import type { EndpointSpec } from "../../types";
import { EndpointForm } from "./EndpointForm";
import { EndpointTemplates } from "./EndpointTemplates";

interface Props {
  endpoints: EndpointSpec[];
  onChange: (endpoints: EndpointSpec[]) => void;
}

export function EndpointList({ endpoints, onChange }: Props) {
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
      <EndpointTemplates existing={endpoints} onAdd={(ep) => onChange([...endpoints, ep])} />

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
