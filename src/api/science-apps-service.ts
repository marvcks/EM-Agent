import { getAgentServerHeaders } from "./agent-server-config";

// This service belongs to EM-Agent, not the SDK. Always use the served origin;
// switching the conversation backend must never send its credentials here.
export const SCIENCE_APPS_PATH = "/science-apps";
const SCIENCE_API_PREFIX = "/api/science";
export const SCIENCE_JOB_PARAM = "job";
export const SCIENCE_EXAMPLE_XYZ =
  "3\nWater\nO 0 0 0\nH 0.7586 0 0.5043\nH -0.7586 0 0.5043\n";
export const SCIENCE_MAGUS_EXAMPLE_XYZ =
  "5\nMethane\nC 0 0 0\nH 0.63 0.63 0.63\nH -0.63 -0.63 0.63\nH -0.63 0.63 -0.63\nH 0.63 -0.63 -0.63\n";
export const SCIENCE_APP_IDS = ["xtb", "orca", "gaussian", "magus"] as const;
export type ScienceAppId = (typeof SCIENCE_APP_IDS)[number];
export type ScienceJobStatus =
  | "queued"
  | "running"
  | "succeeded"
  | "failed"
  | "cancelled";
export interface ScienceApplication {
  id: ScienceAppId;
  name: string;
  category: "semiempirical" | "quantum" | "crystal";
  available: boolean;
  methods: string[];
  bases: string[];
  max_cores: number;
  max_memory_mb: number;
  timeout_seconds: number;
}
export interface ScienceJobRequest {
  app_id: ScienceAppId;
  xyz: string;
  title: string;
  task: "energy" | "optimize" | "search";
  method: string;
  basis: string;
  charge: number;
  multiplicity: number;
  cores: number;
  memory_mb: number;
  model_size?: "small" | "medium" | "large";
  molecules_per_cell?: number;
  population_size?: number;
  generations?: number;
  volume_min?: number;
  volume_max?: number;
}
export interface ScienceJob {
  id: string;
  app_id: ScienceAppId;
  title: string;
  status: ScienceJobStatus;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  energy_hartree: number | null;
  energy_ev?: number | null;
  exit_code: number | null;
}
export interface ScienceJobDetail extends ScienceJob {
  request: ScienceJobRequest;
  log: string;
  files: { name: string; size: number }[];
}
export class ScienceApiError extends Error {
  constructor(public code: string) {
    super(code);
  }
}
async function request(path: string, options?: RequestInit): Promise<Response> {
  const response = await fetch(`${SCIENCE_API_PREFIX}${path}`, {
    ...options,
    headers: { ...getAgentServerHeaders(), ...options?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ScienceApiError(
      typeof body?.detail === "string" ? body.detail : "request_failed",
    );
  }
  return response;
}
async function json<T>(path: string, options?: RequestInit): Promise<T> {
  return (await request(path, options)).json();
}
export const scienceAppsService = {
  apps: () => json<ScienceApplication[]>("/apps"),
  jobs: () => json<ScienceJob[]>("/jobs"),
  job: (id: string) =>
    json<ScienceJobDetail>(`/jobs/${encodeURIComponent(id)}`),
  submit: (input: ScienceJobRequest) =>
    json<ScienceJob>("/jobs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    }),
  cancel: (id: string) =>
    json<ScienceJobDetail>(`/jobs/${encodeURIComponent(id)}/cancel`, {
      method: "POST",
    }),
  download: async (id: string, name: string) => {
    const response = await request(
      `/jobs/${encodeURIComponent(id)}/files/${encodeURIComponent(name)}`,
    );
    const url = URL.createObjectURL(await response.blob());
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  },
};
