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
export const SCIENCE_APP_IDS = [
  "mineru",
  "xtb",
  "orca",
  "gaussian",
  "magus",
  "crystal-morphology",
  "aizynthfinder",
  "lcms2yield",
  "bde",
] as const;
export const SCIENCE_MORPHOLOGY_FEATURES = [
  "添加剂百分比",
  "反溶剂温度(°C)",
  "搅拌速率(rpm)",
  "浓度(g/ml)",
  "溶剂/反溶剂比值",
] as const;
export const SCIENCE_MORPHOLOGY_EXAMPLE_CSV =
  "添加剂百分比,反溶剂温度(°C),搅拌速率(rpm),浓度(g/ml),溶剂/反溶剂比值\n1,10,300,0.06,0.125\n5,5,300,0.06,0.167\n";
export const SCIENCE_ROUTE_EXAMPLE = "CC(=O)Oc1ccccc1C(=O)O";
export const SCIENCE_CF_EXAMPLE =
  "CN(N=C1)C=C1CC2(CC(F)(F)C2)NC(CC3=CC(C=C(Br)C=N4)=C4C=C3)C5=C(O)C=CC=N5";
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
  category:
    | "semiempirical"
    | "quantum"
    | "crystal"
    | "reaction"
    | "bond"
    | "document";
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
  smiles?: string;
  input_kind?: "smiles" | "name";
  compound_name?: string;
  title: string;
  task:
    | "energy"
    | "optimize"
    | "search"
    | "retrosynthesis"
    | "correction_factor"
    | "bde"
    | "textify"
    | "classification";
  document_name?: string;
  language?: "en" | "ch";
  enable_formula?: boolean;
  enable_table?: boolean;
  method: string;
  basis: string;
  charge: number;
  multiplicity: number;
  cores: number;
  memory_mb: number;
  input_mode?: "single" | "batch";
  table_csv?: string;
  additive_percent?: number;
  antisolvent_temp_c?: number;
  stirring_rpm?: number;
  concentration_g_ml?: number;
  solvent_ratio?: number;
  model_size?: "small" | "medium" | "large";
  molecules_per_cell?: number;
  population_size?: number;
  generations?: number;
  volume_min?: number;
  volume_max?: number;
  iterations?: number;
  search_seconds?: number;
  max_transforms?: number;
  max_routes?: number;
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
  result?: {
    markdown_file?: string;
    markdown_characters?: number;
    bundle_file?: string;
    source_name?: string;
    mode?: "ALFABET" | "Psi4";
    canonical_smiles?: string;
    diagram_png_base64?: string;
    minimum_bond_index?: number;
    minimum_bde_kcal_mol?: number;
    bonds?: {
      bond_index: number;
      atom1: number;
      atom2: number;
      bond_type: string;
      status: "ok" | "unsupported";
      reason: string;
      bde_kcal_mol: number | null;
      fragments: string[];
    }[];
    route_count?: number;
    solved_count?: number;
    correction_factors?: { smiles: string; cf: number }[];
    model_id?: string;
    prediction_count?: number;
    class_counts?: Record<string, number>;
    outside_training_range_count?: number;
    rows?: {
      index: number;
      features: Record<string, number>;
      predicted_label: string;
      probabilities: Record<string, number>;
      in_training_range: boolean;
    }[];
  };
  exit_code: number | null;
}
export interface ScienceJobDetail extends ScienceJob {
  request: ScienceJobRequest;
  log: string;
  files: { name: string; size: number }[];
}
export const MAX_SCIENCE_DOCUMENT_BYTES = 20 * 1024 * 1024;
export interface ScienceDocumentOptions {
  title: string;
  method: "vlm" | "pipeline";
  language: "en" | "ch";
  enable_formula: boolean;
  enable_table: boolean;
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
  submitDocument: (file: File, options: ScienceDocumentOptions) => {
    const query = new URLSearchParams({ filename: file.name });
    Object.entries(options).forEach(([key, value]) =>
      query.set(key, String(value)),
    );
    return json<ScienceJob>(`/documents?${query}`, {
      method: "POST",
      headers: { "Content-Type": "application/octet-stream" },
      body: file,
    });
  },
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
