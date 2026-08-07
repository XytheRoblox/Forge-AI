import { useState } from "react";
import type { CronJobSpec } from "../../types";
import { newId } from "../../utils";

interface Props {
  jobs: CronJobSpec[];
  onChange: (jobs: CronJobSpec[]) => void;
}

export function CronJobList({ jobs, onChange }: Props) {
  const [expr, setExpr] = useState("0 9 * * *");
  const [instruction, setInstruction] = useState("");

  function handleAdd() {
    if (!expr.trim() || !instruction.trim()) return;
    onChange([...jobs, { id: newId("cron"), cron_expression: expr.trim(), instruction: instruction.trim() }]);
    setInstruction("");
  }

  function handleRemove(id: string) {
    onChange(jobs.filter((j) => j.id !== id));
  }

  return (
    <div className="cron-editor">
      {jobs.length > 0 && (
        <ul className="cron-list">
          {jobs.map((j) => (
            <li key={j.id} className="cron-item">
              <code>{j.cron_expression}</code>
              <span>{j.instruction}</span>
              <button className="btn-icon" onClick={() => handleRemove(j.id)} title="Remove">
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
      <div className="cron-form-row">
        <input
          className="cron-expr-input"
          value={expr}
          onChange={(e) => setExpr(e.target.value)}
          placeholder="0 9 * * *"
        />
        <input
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="What should the agent do on this schedule?"
        />
        <button onClick={handleAdd}>+ Add</button>
      </div>
    </div>
  );
}
