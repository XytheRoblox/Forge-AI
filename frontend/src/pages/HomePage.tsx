import type { Agent, ModelOption } from "../types";
import { initials, timeAgo } from "../utils";

interface Props {
  agents: Agent[];
  models: ModelOption[];
  onOpen: (agent: Agent) => void;
  onNew: () => void;
  onDelete: (id: number) => void;
}

export function HomePage({ agents, models, onOpen, onNew, onDelete }: Props) {
  const deployedCount = agents.filter((a) => a.status === "deployed").length;

  function modelLabel(agent: Agent): string {
    const match = models.find(
      (m) => m.provider === agent.model_provider && m.model_id === agent.model_id
    );
    return match?.label ?? agent.model_id;
  }

  return (
    <div className="home-page">
      <div className="home-hero">
        <div>
          <h1>Your agents</h1>
          <p>Build a working AI agent in five steps, then deploy it into its own container.</p>
        </div>
        <button className="btn-primary btn-large" onClick={onNew}>
          + New Agent
        </button>
      </div>

      <div className="home-stats">
        <div className="home-stat">
          <span className="stat-value">{agents.length}</span>
          <span className="stat-label">total agents</span>
        </div>
        <div className="home-stat">
          <span className="stat-value">{deployedCount}</span>
          <span className="stat-label">running now</span>
        </div>
        <div className="home-stat">
          <span className="stat-value">{agents.length - deployedCount}</span>
          <span className="stat-label">drafts</span>
        </div>
      </div>

      {agents.length === 0 ? (
        <div className="home-empty">
          <div className="empty-icon">✦</div>
          <h2>No agents yet</h2>
          <p>Create your first agent to get started.</p>
          <button className="btn-primary" onClick={onNew}>
            + New Agent
          </button>
        </div>
      ) : (
        <div className="agent-grid">
          {agents.map((agent) => (
            <div key={agent.id} className="agent-card" onClick={() => onOpen(agent)}>
              <div className="agent-card-top">
                <div className="agent-avatar large">{initials(agent.name)}</div>
                <span className={`badge badge-${agent.status}`}>
                  {agent.status === "deployed" && <span className="pulse-dot" />}
                  {agent.status}
                </span>
              </div>
              <h3>{agent.name}</h3>
              <p className="agent-card-model">{modelLabel(agent)}</p>
              <div className="agent-card-meta">
                {agent.capability_keys.length > 0 && (
                  <span>
                    {agent.capability_keys.length}{" "}
                    {agent.capability_keys.length === 1 ? "capability" : "capabilities"}
                  </span>
                )}
                <span>{timeAgo(agent.created_at)}</span>
              </div>
              <button
                className="btn-icon agent-card-delete"
                onClick={(e) => {
                  e.stopPropagation();
                  onDelete(agent.id);
                }}
                title="Delete agent"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
