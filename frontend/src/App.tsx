import { useEffect, useState } from "react";
import { api } from "./api";
import { Header } from "./components/Header";
import { ToastStack, useToasts } from "./components/Toasts";
import { Wizard } from "./components/wizard/Wizard";
import { AgentPage } from "./pages/AgentPage";
import { BuildingPage } from "./pages/BuildingPage";
import { HomePage } from "./pages/HomePage";
import type { Agent, CapabilityOption, ModelOption } from "./types";
import "./App.css";

type View =
  | { name: "home" }
  | { name: "wizard"; agentId: number | null }
  | { name: "building"; agentId: number; jobId: string }
  | { name: "agent"; agentId: number };

function App() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [models, setModels] = useState<ModelOption[]>([]);
  const [capabilities, setCapabilities] = useState<CapabilityOption[]>([]);
  const [view, setView] = useState<View>({ name: "home" });
  const [loadError, setLoadError] = useState<string | null>(null);
  const [dockerAvailable, setDockerAvailable] = useState<boolean | null>(null);
  const { toasts, notify } = useToasts();

  async function refreshAgents() {
    const list = await api.listAgents();
    setAgents(list);
    return list;
  }

  useEffect(() => {
    Promise.all([api.listModels(), api.listCapabilities(), refreshAgents()])
      .then(([modelList, capList]) => {
        setModels(modelList);
        setCapabilities(capList);
      })
      .catch((e) => setLoadError(e.message));
    api.dockerStatus().then((s) => setDockerAvailable(s.available));
  }, []);

  function goHome() {
    setView({ name: "home" });
  }

  function handleOpen(agent: Agent) {
    if (agent.status === "deployed") {
      setView({ name: "agent", agentId: agent.id });
    } else {
      setView({ name: "wizard", agentId: agent.id });
    }
  }

  function handleNew() {
    setView({ name: "wizard", agentId: null });
  }

  async function handleDelete(id: number) {
    const agent = agents.find((a) => a.id === id);
    await api.deleteAgent(id);
    if (agent) notify(`"${agent.name}" deleted.`);
    await refreshAgents();
  }

  async function handleSaved() {
    await refreshAgents();
    goHome();
  }

  function handleBuildStarted(agentId: number, jobId: string) {
    setView({ name: "building", agentId, jobId });
  }

  async function handleBuildSucceeded(agentId: number) {
    await refreshAgents();
    setDockerAvailable(true);
    setView({ name: "agent", agentId });
  }

  function handleBuildFailed(agentId: number) {
    setView({ name: "wizard", agentId });
  }

  async function handleStopped() {
    await refreshAgents();
    goHome();
  }

  async function handleRebuild(agent: Agent) {
    try {
      const { job_id } = await api.startBuild(agent.id);
      setView({ name: "building", agentId: agent.id, jobId: job_id });
    } catch (e) {
      notify((e as Error).message, "error");
    }
  }

  const wizardAgent =
    view.name === "wizard" && view.agentId !== null
      ? agents.find((a) => a.id === view.agentId) ?? null
      : null;
  const currentAgent =
    view.name === "agent" ? agents.find((a) => a.id === view.agentId) ?? null : null;

  return (
    <div className="app-shell">
      <Header dockerAvailable={dockerAvailable} onHome={goHome} />
      <div className="app-body">
        {loadError && <div className="error page-error">{loadError}</div>}

        {view.name === "home" && (
          <HomePage
            agents={agents}
            models={models}
            onOpen={handleOpen}
            onNew={handleNew}
            onDelete={handleDelete}
          />
        )}

        {view.name === "wizard" && (
          <Wizard
            key={view.agentId ?? "new"}
            agent={wizardAgent}
            models={models}
            capabilities={capabilities}
            dockerAvailable={dockerAvailable}
            onCancel={goHome}
            onSaved={handleSaved}
            onBuildStarted={handleBuildStarted}
            notify={notify}
          />
        )}

        {view.name === "building" && (
          <BuildingPage
            key={view.jobId}
            agentId={view.agentId}
            jobId={view.jobId}
            onSuccess={() => handleBuildSucceeded(view.agentId)}
            onBack={() => handleBuildFailed(view.agentId)}
          />
        )}

        {view.name === "agent" && currentAgent && (
          <AgentPage
            agent={currentAgent}
            onBack={goHome}
            onStopped={handleStopped}
            onRebuild={handleRebuild}
            notify={notify}
          />
        )}
      </div>
      <ToastStack toasts={toasts} />
    </div>
  );
}

export default App;
