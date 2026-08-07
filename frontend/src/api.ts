import type { Agent, BuildJob, CapabilityOption, ChatMessage, ModelOption } from "./types";

const BASE_URL = "http://localhost:8000/api";

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${response.status}`);
  }
  if (response.status === 204) return undefined as T;
  return response.json();
}

export const api = {
  listModels: () => request<ModelOption[]>("/models"),
  listCapabilities: () => request<CapabilityOption[]>("/capabilities"),
  dockerStatus: () => request<{ available: boolean }>("/docker/status"),

  listAgents: () => request<Agent[]>("/agents"),
  getAgent: (id: number) => request<Agent>(`/agents/${id}`),
  createAgent: (payload: Partial<Agent>) =>
    request<Agent>("/agents", { method: "POST", body: JSON.stringify(payload) }),
  updateAgent: (id: number, payload: Partial<Agent>) =>
    request<Agent>(`/agents/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  deleteAgent: (id: number) => request<void>(`/agents/${id}`, { method: "DELETE" }),

  expandManifesto: (id: number, manifesto: string) =>
    request<{ system_prompt: string }>(`/agents/${id}/expand-manifesto`, {
      method: "POST",
      body: JSON.stringify({ manifesto }),
    }),

  startBuild: (id: number) =>
    request<{ job_id: string }>(`/agents/${id}/build`, { method: "POST" }),
  getBuildStatus: (id: number, jobId: string) =>
    request<BuildJob>(`/agents/${id}/build/${jobId}`),
  stopAgent: (id: number) => request<Agent>(`/agents/${id}/stop`, { method: "POST" }),
  updateTheme: (id: number, theme_color: string) =>
    request<Agent>(`/agents/${id}/theme`, {
      method: "PATCH",
      body: JSON.stringify({ theme_color }),
    }),

  getMessages: (id: number) => request<ChatMessage[]>(`/agents/${id}/messages`),
  sendMessage: (id: number, message: string) =>
    request<{ reply: ChatMessage; history: ChatMessage[] }>(`/agents/${id}/chat`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
};
