export interface ModelOption {
  provider: string;
  provider_label: string;
  family: string;
  family_label: string;
  model_id: string;
  label: string;
  description: string;
  available: boolean;
}

export interface ModelRecommendation {
  model_id: string;
  provider: string;
  label: string;
  reason: string;
}

export interface CapabilityOption {
  key: string;
  name: string;
  description: string;
  icon: string;
  wired: boolean;
  mcp_server: string | null;
  requires_api_key: boolean;
  api_key_help: string | null;
  platform_key_available: boolean;
  oauth_provider: string | null;
  oauth_scopes: string[];
}

export interface EndpointSpec {
  id: string;
  path: string;
  method: string;
  description: string;
  input_schema: Record<string, unknown>;
  instruction: string;
}

export interface CapabilityRecommendation {
  key: string;
  name: string;
  icon: string;
  reason: string;
}

/** A ready-made endpoint from the catalog. Everything from `path` down is
 * the EndpointSpec it produces; the fields above it are only for the picker. */
export interface EndpointTemplate {
  key: string;
  name: string;
  icon: string;
  summary: string;
  path: string;
  method: string;
  description: string;
  input_schema: Record<string, unknown>;
  instruction: string;
  suggested_capability: string | null;
  suggested_capability_name: string | null;
}

export interface CronJobSpec {
  id: string;
  cron_expression: string;
  instruction: string;
}

export interface Agent {
  id: number;
  name: string;
  model_provider: string;
  model_id: string;
  hosting_mode: string;
  manifesto: string | null;
  system_prompt: string | null;
  has_model_api_key: boolean;
  capability_keys: string[];
  capability_api_keys_set: string[];
  connected_accounts: Record<string, string>;
  endpoints: EndpointSpec[];
  cron_jobs: CronJobSpec[];
  theme_color: string;
  status: "draft" | "deployed";
  created_at: string;
  deployed_at: string | null;
  container_id: string | null;
  container_port: number | null;
  service_url: string | null;
  cloudrun_service_name: string | null;
}

export interface ChatMessage {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface BuildStep {
  name: string;
  status: "pending" | "running" | "success" | "failed";
  detail: string | null;
}

export interface BuildJob {
  id: string;
  agent_id: number;
  status: "running" | "success" | "failed";
  steps: BuildStep[];
}
