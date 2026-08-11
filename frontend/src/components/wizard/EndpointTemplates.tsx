import { useEffect, useState } from "react";
import { api } from "../../api";
import type { EndpointSpec, EndpointTemplate } from "../../types";
import { newId } from "../../utils";

interface Props {
  /** Already-attached endpoints, so a template that's in can say so. */
  existing: EndpointSpec[];
  onAdd: (endpoint: EndpointSpec) => void;
  /** What this agent is for. Empty means no tailored suggestions, only the
   * stock templates below them. */
  agentName?: string;
  purpose?: string;
  capabilityKeys?: string[];
}

function toSpec(t: EndpointTemplate): EndpointSpec {
  return {
    id: newId(),
    path: t.path,
    method: t.method,
    description: t.description,
    input_schema: t.input_schema,
    instruction: t.instruction,
  };
}

/** One-click endpoints, so nobody has to invent a JSON Schema and a prompt
 * from a blank form to see what endpoints are for.
 *
 * Two sources, in order of how likely they are to be what you want: endpoints
 * written for this specific agent by a model that read its manifesto, then the
 * stock nine. Either source failing leaves the other — and the manual form
 * below — untouched. */
export function EndpointTemplates({
  existing,
  onAdd,
  agentName = "",
  purpose = "",
  capabilityKeys = [],
}: Props) {
  const [templates, setTemplates] = useState<EndpointTemplate[]>([]);
  const [suggested, setSuggested] = useState<EndpointTemplate[]>([]);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestNote, setSuggestNote] = useState("");
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

  // Asked once per purpose, like the model recommendation on the Model step.
  // `existing` is deliberately not a dependency — re-suggesting every time
  // someone attaches an endpoint would replace the list they're clicking on.
  useEffect(() => {
    if (!purpose.trim()) {
      setSuggested([]);
      return;
    }
    let cancelled = false;
    setSuggesting(true);
    api
      .suggestEndpoints({
        name: agentName,
        purpose,
        capability_keys: capabilityKeys,
        taken_paths: existing.map((e) => e.path),
      })
      .then((r) => {
        if (cancelled) return;
        setSuggested(r.recommendations);
        setSuggestNote(r.unavailable ?? "");
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setSuggesting(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [purpose, agentName, capabilityKeys.join(",")]);

  if (templates.length === 0 && suggested.length === 0 && !suggesting) return null;

  // Two endpoints on the same method and path would register two routes on
  // the agent, and only the first would ever be reached.
  const taken = new Set(existing.map((e) => `${e.method} ${e.path}`));

  const card = (t: EndpointTemplate) => {
    const added = taken.has(`${t.method} ${t.path}`);
    return (
      <button
        key={t.key}
        type="button"
        className={`option-card ${added ? "disabled" : ""}`}
        disabled={added}
        onClick={() => onAdd(toSpec(t))}
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
  };

  return (
    <>
      {(suggesting || suggested.length > 0 || suggestNote) && (
        <div className="endpoint-suggestions">
          <div className="endpoint-suggestions-head">
            <span>Suggested for this agent</span>
            {suggesting && <span className="field-hint">Reading what this agent is for…</span>}
            {!suggesting && suggestNote && <span className="field-hint">{suggestNote}</span>}
          </div>
          {suggested.length > 0 && <div className="option-card-grid">{suggested.map(card)}</div>}
        </div>
      )}

      <details
        className="collapsible endpoint-templates"
        open={open}
        onToggle={(e) => setOpen(e.currentTarget.open)}
      >
        <summary>
          <span>Start from a template</span>
          <span className="model-count-badge">{templates.length}</span>
        </summary>
        <div className="option-card-grid">{templates.map(card)}</div>
      </details>
    </>
  );
}
