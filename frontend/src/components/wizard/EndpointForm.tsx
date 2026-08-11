import { useState } from "react";
import type { EndpointSpec } from "../../types";
import { newId } from "../../utils";

interface FieldRow {
  name: string;
  type: string;
  required: boolean;
}

interface Props {
  onAdd: (endpoints: EndpointSpec[]) => void;
  onCancel: () => void;
}

function fieldsToSchema(fields: FieldRow[]): Record<string, unknown> {
  const properties: Record<string, { type: string }> = {};
  const required: string[] = [];
  for (const f of fields) {
    if (!f.name.trim()) continue;
    properties[f.name.trim()] = { type: f.type };
    if (f.required) required.push(f.name.trim());
  }
  return { type: "object", properties, required };
}

/** Best-effort OpenAPI/Swagger (or bare JSON Schema) parser: one endpoint per
 * operation for OpenAPI documents, or a single endpoint for a bare schema.
 * Doesn't resolve $ref — inline schemas only. */
function parseSpec(text: string): EndpointSpec[] {
  const doc = JSON.parse(text);

  if (doc.paths && typeof doc.paths === "object") {
    const endpoints: EndpointSpec[] = [];
    for (const [path, operations] of Object.entries<Record<string, unknown>>(doc.paths)) {
      for (const [method, op] of Object.entries(operations)) {
        if (!["get", "post", "put", "patch", "delete"].includes(method)) continue;
        const operation = op as {
          summary?: string;
          description?: string;
          requestBody?: { content?: Record<string, { schema?: Record<string, unknown> }> };
        };
        const schema =
          operation.requestBody?.content?.["application/json"]?.schema ??
          ({ type: "object", properties: {} } as Record<string, unknown>);
        endpoints.push({
          id: newId(),
          path,
          method: method.toUpperCase(),
          description: operation.summary || operation.description || "",
          input_schema: schema,
          instruction: operation.description || operation.summary || "",
        });
      }
    }
    if (endpoints.length === 0) {
      throw new Error("No operations found in that OpenAPI document.");
    }
    return endpoints;
  }

  // Treat as a bare JSON Schema for a single endpoint.
  return [
    {
      id: newId(),
      path: "/custom",
      method: "POST",
      description: "",
      input_schema: doc,
      instruction: "",
    },
  ];
}

export function EndpointForm({ onAdd, onCancel }: Props) {
  const [mode, setMode] = useState<"visual" | "spec">("visual");
  const [path, setPath] = useState("/custom");
  const [method, setMethod] = useState("POST");
  const [description, setDescription] = useState("");
  const [instruction, setInstruction] = useState("");
  const [fields, setFields] = useState<FieldRow[]>([{ name: "", type: "string", required: true }]);
  const [specText, setSpecText] = useState("");
  const [error, setError] = useState<string | null>(null);

  function updateField(index: number, patch: Partial<FieldRow>) {
    setFields((prev) => prev.map((f, i) => (i === index ? { ...f, ...patch } : f)));
  }

  function addFieldRow() {
    setFields((prev) => [...prev, { name: "", type: "string", required: false }]);
  }

  function removeFieldRow(index: number) {
    setFields((prev) => prev.filter((_, i) => i !== index));
  }

  function handleAddVisual() {
    if (!path.trim() || !instruction.trim()) {
      setError("Path and instruction are required.");
      return;
    }
    onAdd([
      {
        id: newId(),
        path: path.trim(),
        method,
        description,
        input_schema: fieldsToSchema(fields),
        instruction,
      },
    ]);
  }

  function handleParseSpec() {
    try {
      const parsed = parseSpec(specText);
      onAdd(parsed);
    } catch (e) {
      setError((e as Error).message || "Could not parse that as JSON.");
    }
  }

  return (
    <div className="endpoint-form">
      <div className="toggle-group">
        <button
          className={mode === "visual" ? "toggle active" : "toggle"}
          onClick={() => setMode("visual")}
        >
          Visual fields
        </button>
        <button
          className={mode === "spec" ? "toggle active" : "toggle"}
          onClick={() => setMode("spec")}
        >
          Paste OpenAPI/JSON
        </button>
      </div>

      {mode === "visual" && (
        <>
          <div className="endpoint-form-row">
            <select value={method} onChange={(e) => setMethod(e.target.value)}>
              <option>POST</option>
              <option>GET</option>
              <option>PUT</option>
              <option>PATCH</option>
            </select>
            <input value={path} onChange={(e) => setPath(e.target.value)} placeholder="/custom" />
          </div>
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Short description (e.g. 'Look up an order by id')"
          />
          <textarea
            value={instruction}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder="Instruction: how should the agent turn this input into a response?"
            rows={2}
          />

          <span className="field-hint">Input fields (compiled into a JSON Schema)</span>
          <div className="field-rows">
            {fields.map((f, i) => (
              <div key={i} className="field-row">
                <input
                  value={f.name}
                  onChange={(e) => updateField(i, { name: e.target.value })}
                  placeholder="field name"
                />
                <select value={f.type} onChange={(e) => updateField(i, { type: e.target.value })}>
                  <option value="string">string</option>
                  <option value="number">number</option>
                  <option value="boolean">boolean</option>
                  <option value="array">array</option>
                  <option value="object">object</option>
                </select>
                <label className="field-row-required">
                  <input
                    type="checkbox"
                    checked={f.required}
                    onChange={(e) => updateField(i, { required: e.target.checked })}
                  />
                  required
                </label>
                <button className="btn-icon" onClick={() => removeFieldRow(i)} title="Remove field">
                  ×
                </button>
              </div>
            ))}
            <button onClick={addFieldRow}>+ Add field</button>
          </div>

          {error && <div className="error">{error}</div>}
          <div className="actions">
            <button onClick={onCancel}>Cancel</button>
            <button className="btn-primary" onClick={handleAddVisual}>
              Add endpoint
            </button>
          </div>
        </>
      )}

      {mode === "spec" && (
        <>
          <textarea
            value={specText}
            onChange={(e) => setSpecText(e.target.value)}
            placeholder="Paste an OpenAPI/Swagger JSON document, or a bare JSON Schema…"
            rows={8}
          />
          <input
            type="file"
            accept=".json,application/json"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (!file) return;
              file.text().then(setSpecText);
            }}
          />
          {error && <div className="error">{error}</div>}
          <div className="actions">
            <button onClick={onCancel}>Cancel</button>
            <button className="btn-primary" onClick={handleParseSpec} disabled={!specText.trim()}>
              Parse & add
            </button>
          </div>
        </>
      )}
    </div>
  );
}
