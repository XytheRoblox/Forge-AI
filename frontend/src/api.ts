import type {
  Agent,
  BuildJob,
  CapabilityOption,
  CapabilityRecommendation,
  ChatMessage,
  EndpointTemplate,
  ModelOption,
  ModelRecommendation,
} from "./types";

// Relative by design — see the proxy note in vite.config.ts. An absolute
// localhost URL only works when the browser is on the same machine as the
// backend, which stops being true the moment the app is tunnelled.
const BASE_URL = "/api";

// The API's shared secret, when this instance has one. It arrives once as
// ?access_token=… on the URL — the link you'd send someone — and is kept in
// localStorage after that, so a reload or a deep link still works. Stripped
// from the address bar immediately so it isn't left in screen shares,
// bookmarks or the browser history.
const TOKEN_KEY = "forge_access_token";

function readAccessToken(): string {
  const url = new URL(window.location.href);
  const fromUrl = url.searchParams.get("access_token");
  if (fromUrl) {
    localStorage.setItem(TOKEN_KEY, fromUrl);
    url.searchParams.delete("access_token");
    window.history.replaceState({}, "", url.toString());
    return fromUrl;
  }
  return localStorage.getItem(TOKEN_KEY) ?? "";
}

let accessToken = readAccessToken();

/** A URL the BROWSER will navigate to — an iframe src, a new tab — carrying
 * the token as a query parameter.
 *
 * Navigations can't set a custom header the way fetch() can, so the header
 * this module adds everywhere else is unavailable to them. The API accepts
 * the token as a query parameter for exactly this case and replies with a
 * cookie, so anything the loaded page requests afterwards is authenticated
 * without the token appearing again. */
export function withAccessToken(path: string): string {
  if (!accessToken) return path;
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}access_token=${encodeURIComponent(accessToken)}`;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(accessToken ? { "X-Forge-Token": accessToken } : {}),
      ...(options?.headers ?? {}),
    },
  });
  if (response.status === 401) {
    // A stale token is worse than none: it would fail silently on every
    // request until someone cleared storage by hand.
    localStorage.removeItem(TOKEN_KEY);
    accessToken = "";
    throw new Error(
      "This Forge instance needs an access token. Open it with ?access_token=… on the URL."
    );
  }
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
  recommendCapabilities: (purpose: string) =>
    request<{ recommendations: CapabilityRecommendation[]; unavailable?: string }>("/capabilities/recommend", {
      method: "POST",
      body: JSON.stringify({ purpose }),
    }),
  listEndpointTemplates: () => request<EndpointTemplate[]>("/endpoint-templates"),
  suggestEndpoints: (payload: {
    name: string;
    purpose: string;
    capability_keys: string[];
    taken_paths: string[];
  }) =>
    request<{ recommendations: EndpointTemplate[]; unavailable?: string }>("/endpoint-templates/recommend", {
      method: "POST",
      body: JSON.stringify(payload),
    }),
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
  restartAgent: (id: number) => request<Agent>(`/agents/${id}/restart`, { method: "POST" }),
  regenerateWebpage: (id: number) =>
    request<Agent>(`/agents/${id}/regenerate-webpage`, { method: "POST" }),
  updateTheme: (id: number, theme_color: string) =>
    request<Agent>(`/agents/${id}/theme`, {
      method: "PATCH",
      body: JSON.stringify({ theme_color }),
    }),

  googleOAuthStatus: () => request<{ configured: boolean; redirect_uri: string }>("/oauth/google/status"),
  startGoogleOAuth: (agentId: number) =>
    request<{ authorization_url: string }>(`/oauth/google/start/${agentId}`, { method: "POST" }),
  disconnectGoogle: (agentId: number) =>
    request<{ connected: boolean }>(`/oauth/google/${agentId}`, { method: "DELETE" }),

  recommendModel: (purpose: string) =>
    request<{ recommendation: ModelRecommendation | null }>("/models/recommend", {
      method: "POST",
      body: JSON.stringify({ purpose }),
    }),

  getMessages: (id: number) => request<ChatMessage[]>(`/agents/${id}/messages`),
  sendMessage: (id: number, message: string) =>
    request<{ reply: ChatMessage; history: ChatMessage[] }>(`/agents/${id}/chat`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
};
