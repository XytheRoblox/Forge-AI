import type { CronJobSpec, EndpointSpec } from "../../types";

export interface WizardState {
  name: string;
  model_provider: string;
  model_id: string;
  hosting_mode: string;
  model_api_key: string;
  capability_keys: string[];
  capability_api_keys: Record<string, string>;
  endpoints: EndpointSpec[];
  cron_jobs: CronJobSpec[];
  theme_color: string;
  manifesto: string;
  system_prompt: string;
}

export interface StepProps {
  state: WizardState;
  update: (patch: Partial<WizardState>) => void;
}
