import { useEffect, useState } from "react";
import { api } from "../../api";
import type { EndpointSpec, EndpointTemplate } from "../../types";
import { newId } from "../../utils";

interface Props {
  /** Already-attached endpoints, so a template that's in can say so. */
  existing: EndpointSpec[];
  onAdd: (endpoint: EndpointSpec) => void;
}

/** One-click endpoints, so nobody has to invent a JSON Schema and a prompt
 * from a blank form to see what endpoints are for.
 *
 * Catalog data rather than a local constant: the templates name capability
 * keys, which only the backend registry knows. A fetch failure just hides the
 * picker — the manual form below it is unaffected. */
export function EndpointTemplates({ existing, onAdd }: Props) {
  const [templates, setTemplates] = useState<EndpointTemplate[]>([]);
  // Open state has to be held, not derived: deriving it from
  // `existing.length === 0` slammed the panel shut the moment you added your
  // first template, so a second one took two clicks.
  const [open, setOpen] = useState(existing.length === 0);

  useEffect(() => {
    let cancelled = false;
    api
      .listEndpointTemplates()
      .then((t) => {
        if (!cancelled) setTemplates(t);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  if (templates.length === 0) return null;

  // Two endpoints on the same method and path would register two routes on
  // the agent, and only the first would ever be reached.
  const taken = new Set(existing.map((e) => `${e.method} ${e.path}`));

  return (
    <details
      className="collapsible endpoint-templates"
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>
        <span>Start from a template</span>
        <span className="model-count-badge">{templates.length}</span>
      </summary>
      <div className="option-card-grid">
        {templates.map((t) => {
          const added = taken.has(`${t.method} ${t.path}`);
          return (
            <button
              key={t.key}
              type="button"
              className={`option-card ${added ? "disabled" : ""}`}
              disabled={added}
              onClick={() =>
                onAdd({
                  id: newId(),
                  path: t.path,
                  method: t.method,
                  description: t.description,
                  input_schema: t.input_schema,
                  instruction: t.instruction,
                })
              }
            >
              <div className="option-card-top">
                <span className="option-card-title">
                  {t.icon} {t.name}
                </span>
                {added && <span className="tag">added</span>}
              </div>
              <p className="option-card-desc">{t.summary}</p>
              <code className="endpoint-template-path">
                {t.method} {t.path}
              </code>
              {t.suggested_capability_name && (
                <span className="field-hint">Best with {t.suggested_capability_name}</span>
              )}
            </button>
          );
        })}
      </div>
    </details>
  );
}
