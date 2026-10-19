import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  ArrowUpRight,
  Atom,
  Check,
  Download,
  FlaskConical,
  Play,
  Search,
  Square,
  Upload,
} from "lucide-react";
import { I18nKey } from "#/i18n/declaration";
import { NavigationLink } from "#/components/shared/navigation-link";
import { BrandButton } from "#/components/features/settings/brand-button";
import { SCIENCE_QUERY_KEYS } from "#/hooks/query/query-keys";
import {
  scienceAppsService,
  SCIENCE_APPS_PATH,
  SCIENCE_EXAMPLE_XYZ,
  SCIENCE_MAGUS_EXAMPLE_XYZ,
  SCIENCE_JOB_PARAM,
  ScienceApiError,
  type ScienceApplication,
  type ScienceJobRequest,
  type ScienceJobStatus,
} from "#/api/science-apps-service";

import { ReactionForm } from "./reaction-form";

const DESCRIPTION_KEYS = {
  xtb: I18nKey.SCIENCE$XTB_DESCRIPTION,
  orca: I18nKey.SCIENCE$ORCA_DESCRIPTION,
  gaussian: I18nKey.SCIENCE$GAUSSIAN_DESCRIPTION,
  magus: I18nKey.SCIENCE$MAGUS_DESCRIPTION,
  aizynthfinder: I18nKey.SCIENCE$AIZYNTH_DESCRIPTION,
  lcms2yield: I18nKey.SCIENCE$LCMS_DESCRIPTION,
};
const STATUS_KEYS: Record<ScienceJobStatus, I18nKey> = {
  queued: I18nKey.SCIENCE$QUEUED,
  running: I18nKey.SCIENCE$RUNNING,
  succeeded: I18nKey.SCIENCE$SUCCEEDED,
  failed: I18nKey.SCIENCE$FAILED,
  cancelled: I18nKey.SCIENCE$CANCELLED,
};
const ERROR_KEYS: Record<string, I18nKey> = {
  invalid_smiles: I18nKey.SCIENCE$INVALID_SMILES,
  invalid_reaction_input: I18nKey.SCIENCE$INVALID_SMILES,
  invalid_method: I18nKey.SCIENCE$INVALID_SMILES,
  invalid_xyz: I18nKey.SCIENCE$INVALID_XYZ,
  invalid_spin: I18nKey.SCIENCE$INVALID_SPIN,
  app_unavailable: I18nKey.SCIENCE$UNAVAILABLE,
  queue_full: I18nKey.SCIENCE$QUEUE_FULL,
  timeout: I18nKey.SCIENCE$TIMEOUT,
  service_restarted: I18nKey.SCIENCE$RESTARTED,
  calculation_failed: I18nKey.SCIENCE$CALCULATION_FAILED,
  invalid_magus_molecule: I18nKey.SCIENCE$MAGUS_INPUT_ERROR,
  invalid_volume: I18nKey.SCIENCE$VOLUME_ERROR,
};
const CATEGORY_KEYS = {
  all: I18nKey.SCIENCE$ALL,
  quantum: I18nKey.SCIENCE$QUANTUM,
  semiempirical: I18nKey.SCIENCE$SEMIEMPIRICAL,
  crystal: I18nKey.SCIENCE$CRYSTAL,
  reaction: I18nKey.SCIENCE$REACTION,
};
const SCIENCE_CATEGORIES = [
  "all",
  "quantum",
  "semiempirical",
  "crystal",
  "reaction",
] as const;
const OFF23_MODEL_SIZES = ["small", "medium", "large"] as const;
const SEARCH_FIELDS = [
  {
    key: "molecules_per_cell",
    label: I18nKey.SCIENCE$MOLECULES_PER_CELL,
    min: 1,
    max: 8,
  },
  {
    key: "population_size",
    label: I18nKey.SCIENCE$POPULATION,
    min: 4,
    max: 12,
  },
  { key: "generations", label: I18nKey.SCIENCE$GENERATIONS, min: 1, max: 10 },
  { key: "volume_min", label: I18nKey.SCIENCE$VOLUME_MIN, min: 30, max: 20000 },
  { key: "volume_max", label: I18nKey.SCIENCE$VOLUME_MAX, min: 30, max: 20000 },
] as const;
const isActive = (status?: ScienceJobStatus) =>
  status === "queued" || status === "running";

function ErrorMessage({ error }: { error: unknown }) {
  const { t } = useTranslation("openhands");
  if (!error) return null;
  const code = error instanceof ScienceApiError ? error.code : "request_failed";
  return (
    <p className="em-science-error" role="alert">
      {t(ERROR_KEYS[code] ?? I18nKey.SCIENCE$REQUEST_FAILED)}
    </p>
  );
}

function MoleculeArt() {
  return (
    <svg
      className="em-science-art"
      viewBox="0 0 360 220"
      fill="none"
      aria-hidden="true"
    >
      <defs>
        <radialGradient id="science-atom">
          <stop stopColor="var(--oh-color-base)" />
          <stop offset="1" stopColor="var(--oh-color-primary)" />
        </radialGradient>
      </defs>
      <ellipse
        cx="192"
        cy="115"
        rx="137"
        ry="68"
        stroke="currentColor"
        strokeDasharray="3 7"
        transform="rotate(-20 192 115)"
      />
      <ellipse
        cx="192"
        cy="115"
        rx="92"
        ry="95"
        stroke="currentColor"
        opacity=".4"
        transform="rotate(32 192 115)"
      />
      <path
        d="M92 129 160 65 231 105 274 163 183 177 92 129 231 105 183 177 160 65"
        stroke="currentColor"
        strokeWidth="3"
      />
      {[
        [92, 129, 17],
        [160, 65, 22],
        [231, 105, 29],
        [274, 163, 13],
        [183, 177, 18],
      ].map(([cx, cy, r]) => (
        <circle
          key={cx}
          cx={cx}
          cy={cy}
          r={r}
          fill="url(#science-atom)"
          stroke="var(--oh-surface)"
          strokeWidth="2"
        />
      ))}
      <circle cx="306" cy="58" r="5" fill="var(--oh-color-primary)" />
      <circle cx="55" cy="66" r="3" fill="currentColor" />
    </svg>
  );
}

interface Props {
  appId?: string;
  jobId: string | null;
  onSelectJob: (id: string | null) => void;
}
export function ScienceAppsPage({ appId, jobId, onSelectJob }: Props) {
  const { t } = useTranslation("openhands");
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<keyof typeof CATEGORY_KEYS>("all");
  const apps = useQuery({
    queryKey: SCIENCE_QUERY_KEYS.apps,
    queryFn: scienceAppsService.apps,
    retry: false,
  });
  const jobs = useQuery({
    queryKey: SCIENCE_QUERY_KEYS.jobs,
    queryFn: scienceAppsService.jobs,
    retry: false,
    refetchInterval: (query) =>
      query.state.data?.some((job) => isActive(job.status)) ? 2000 : false,
  });
  const selected = apps.data?.find((app) => app.id === appId);
  const visible =
    apps.data?.filter(
      (app) =>
        (category === "all" || app.category === category) &&
        `${app.name} ${t(DESCRIPTION_KEYS[app.id])}`
          .toLowerCase()
          .includes(search.toLowerCase()),
    ) ?? [];
  return (
    <main className="em-science-page" data-testid="science-apps-page">
      <div className="em-science-content">
        {selected ? (
          <>
            <NavigationLink to={SCIENCE_APPS_PATH} className="em-science-back">
              <ArrowLeft size={15} />
              {t(I18nKey.SCIENCE$BACK)}
            </NavigationLink>
            <div className="em-science-detail-heading">
              <div className="em-science-app-icon">
                <Atom size={27} />
              </div>
              <div>
                <h1>{selected.name}</h1>
                <p>{t(DESCRIPTION_KEYS[selected.id])}</p>
              </div>
              <span
                className="em-science-status"
                data-status={selected.available ? "succeeded" : "failed"}
              >
                {t(
                  selected.available
                    ? I18nKey.SCIENCE$AVAILABLE
                    : I18nKey.SCIENCE$UNAVAILABLE,
                )}
              </span>
            </div>
            <div className="em-science-workbench">
              {selected.category === "reaction" ? (
                <ReactionForm
                  key={selected.id}
                  app={selected}
                  onCreated={onSelectJob}
                  renderError={(error) => <ErrorMessage error={error} />}
                />
              ) : (
                <ScienceForm
                  key={selected.id}
                  app={selected}
                  onCreated={onSelectJob}
                />
              )}
              <JobResult jobId={jobId} />
            </div>
          </>
        ) : (
          <>
            <section className="em-science-hero">
              <div>
                <div className="em-science-kicker">
                  <FlaskConical size={14} />
                  {t(I18nKey.SCIENCE$KICKER)}
                </div>
                <h1>{t(I18nKey.SCIENCE$HERO_TITLE)}</h1>
                <p>{t(I18nKey.SCIENCE$HERO_DESCRIPTION)}</p>
                <span className="em-science-hero-note">
                  <span />
                  {t(I18nKey.SCIENCE$MANUAL_NOTE)}
                </span>
              </div>
              <MoleculeArt />
            </section>
            <div className="em-science-toolbar">
              <div className="em-science-tabs">
                {SCIENCE_CATEGORIES.map((value) => (
                  <button
                    type="button"
                    key={value}
                    aria-pressed={category === value}
                    onClick={() => setCategory(value)}
                  >
                    {t(CATEGORY_KEYS[value])}
                  </button>
                ))}
              </div>
              <label className="em-science-search">
                <Search size={15} />
                <input
                  aria-label={t(I18nKey.SCIENCE$SEARCH)}
                  placeholder={t(I18nKey.SCIENCE$SEARCH)}
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </label>
            </div>
            {apps.isPending && (
              <p role="status">{t(I18nKey.SCIENCE$LOADING)}</p>
            )}
            <ErrorMessage error={apps.error} />
            {apps.isError && (
              <BrandButton
                type="button"
                variant="secondary"
                onClick={() => {
                  void apps.refetch();
                }}
              >
                {t(I18nKey.SCIENCE$RETRY)}
              </BrandButton>
            )}
            <div className="em-science-grid">
              {visible.map((app) => (
                <NavigationLink
                  key={app.id}
                  to={`${SCIENCE_APPS_PATH}/${app.id}`}
                  className="em-science-card"
                  data-testid={`science-app-${app.id}`}
                >
                  <div className="em-science-card-top">
                    <div className="em-science-app-icon">
                      <Atom size={25} />
                    </div>
                    <span
                      className="em-science-status"
                      data-status={app.available ? "succeeded" : "failed"}
                    >
                      {t(
                        app.available
                          ? I18nKey.SCIENCE$AVAILABLE
                          : I18nKey.SCIENCE$UNAVAILABLE,
                      )}
                    </span>
                  </div>
                  <h2>{app.name}</h2>
                  <p>{t(DESCRIPTION_KEYS[app.id])}</p>
                  <div className="em-science-card-tags">
                    <span>{t(CATEGORY_KEYS[app.category])}</span>
                    <span>
                      {t(
                        app.category === "reaction"
                          ? I18nKey.SCIENCE$SMILES_INPUT
                          : I18nKey.SCIENCE$XYZ_INPUT,
                      )}
                    </span>
                  </div>
                  <div className="em-science-card-footer">
                    <span>{t(I18nKey.SCIENCE$OPEN_APP)}</span>
                    <ArrowUpRight size={16} />
                  </div>
                </NavigationLink>
              ))}
            </div>
            {apps.isSuccess && visible.length === 0 && (
              <p className="em-science-empty">{t(I18nKey.SCIENCE$NO_APPS)}</p>
            )}
            <p className="em-science-footnote">
              {t(I18nKey.SCIENCE$FUTURE_NOTE)}
            </p>
          </>
        )}
        <section className="em-science-history">
          <div className="em-science-section-heading">
            <h2>{t(I18nKey.SCIENCE$HISTORY)}</h2>
            <span>{t(I18nKey.SCIENCE$QUEUE_NOTE)}</span>
          </div>
          <ErrorMessage error={jobs.error} />
          {jobs.isPending && <p role="status">{t(I18nKey.SCIENCE$LOADING)}</p>}
          {jobs.data
            ?.filter((job) => !appId || job.app_id === appId)
            .map((job) => (
              <NavigationLink
                key={job.id}
                to={`${SCIENCE_APPS_PATH}/${job.app_id}?${SCIENCE_JOB_PARAM}=${job.id}`}
                className="em-science-history-row"
              >
                <FlaskConical size={17} />
                <div>
                  <strong>{job.title}</strong>
                  <span>{new Date(job.created_at).toLocaleString()}</span>
                </div>
                <span className="em-science-status" data-status={job.status}>
                  {t(STATUS_KEYS[job.status])}
                </span>
                <ArrowUpRight size={15} />
              </NavigationLink>
            ))}
          {jobs.isSuccess &&
            !jobs.data.some((job) => !appId || job.app_id === appId) && (
              <p className="em-science-empty">{t(I18nKey.SCIENCE$NO_JOBS)}</p>
            )}
        </section>
      </div>
    </main>
  );
}

function ScienceForm({
  app,
  onCreated,
}: {
  app: ScienceApplication;
  onCreated: (id: string) => void;
}) {
  const { t } = useTranslation("openhands");
  const queryClient = useQueryClient();
  const isMagus = app.id === "magus";
  const [input, setInput] = useState<ScienceJobRequest>({
    app_id: app.id,
    xyz: "",
    title: "",
    task: isMagus ? "search" : "energy",
    method: app.methods[0],
    basis: app.bases[0] ?? "",
    charge: 0,
    multiplicity: 1,
    cores: 2,
    memory_mb: 2048,
    ...(isMagus
      ? {
          model_size: "medium" as const,
          molecules_per_cell: 4,
          population_size: 6,
          generations: 3,
          volume_min: 180,
          volume_max: 400,
        }
      : {}),
  });
  const [fileName, setFileName] = useState("");
  const [fileError, setFileError] = useState(false);
  const submit = useMutation({
    mutationFn: scienceAppsService.submit,
    onSuccess: (job) => {
      void queryClient.invalidateQueries({ queryKey: SCIENCE_QUERY_KEYS.jobs });
      onCreated(job.id);
    },
  });
  const patch = <K extends keyof ScienceJobRequest>(
    key: K,
    value: ScienceJobRequest[K],
  ) => setInput((current) => ({ ...current, [key]: value }));
  return (
    <form
      className="em-science-panel em-science-form"
      onSubmit={(event) => {
        event.preventDefault();
        submit.mutate(input);
      }}
    >
      <h2>{t(I18nKey.SCIENCE$PARAMETERS)}</h2>
      <label>
        {t(I18nKey.SCIENCE$JOB_TITLE)}
        <input
          maxLength={80}
          value={input.title}
          placeholder={app.name}
          onChange={(event) => patch("title", event.target.value)}
        />
      </label>
      <div className="em-science-section-heading">
        <h3>{t(I18nKey.SCIENCE$STRUCTURE)}</h3>
        <button
          type="button"
          onClick={() => {
            patch(
              "xyz",
              isMagus ? SCIENCE_MAGUS_EXAMPLE_XYZ : SCIENCE_EXAMPLE_XYZ,
            );
            setFileName("");
            setFileError(false);
          }}
        >
          {t(
            isMagus
              ? I18nKey.SCIENCE$USE_METHANE_EXAMPLE
              : I18nKey.SCIENCE$USE_EXAMPLE,
          )}
        </button>
      </div>
      <label className="em-science-upload">
        <Upload size={18} />
        <span>{fileName || t(I18nKey.SCIENCE$UPLOAD_XYZ)}</span>
        <input
          type="file"
          accept=".xyz"
          aria-label={t(I18nKey.SCIENCE$UPLOAD_XYZ)}
          onChange={async (event) => {
            const file = event.target.files?.[0];
            if (!file) return;
            if (
              file.size > 65536 ||
              !file.name.toLowerCase().endsWith(".xyz")
            ) {
              setFileError(true);
              return;
            }
            try {
              patch("xyz", await file.text());
              setFileName(file.name);
              setFileError(false);
            } catch {
              setFileError(true);
            }
          }}
        />
      </label>
      {fileError && (
        <p className="em-science-error" role="alert">
          {t(I18nKey.SCIENCE$FILE_ERROR)}
        </p>
      )}
      <label>
        <span className="sr-only">{t(I18nKey.SCIENCE$XYZ_CONTENT)}</span>
        <textarea
          required
          rows={7}
          maxLength={65536}
          value={input.xyz}
          placeholder={t(I18nKey.SCIENCE$XYZ_PLACEHOLDER)}
          onChange={(event) => {
            patch("xyz", event.target.value);
            setFileName("");
            setFileError(false);
          }}
        />
      </label>
      <p className="em-science-help">
        {t(
          isMagus ? I18nKey.SCIENCE$MAGUS_INPUT_HELP : I18nKey.SCIENCE$XYZ_HELP,
        )}
      </p>
      <div className="em-science-fields">
        <label>
          {t(I18nKey.SCIENCE$TASK)}
          <select
            value={input.task}
            onChange={(event) =>
              patch("task", event.target.value as ScienceJobRequest["task"])
            }
          >
            {isMagus ? (
              <option value="search">
                {t(I18nKey.SCIENCE$CRYSTAL_SEARCH)}
              </option>
            ) : (
              <>
                <option value="energy">{t(I18nKey.SCIENCE$ENERGY)}</option>
                <option value="optimize">{t(I18nKey.SCIENCE$OPTIMIZE)}</option>
              </>
            )}
          </select>
        </label>
        <label>
          {t(I18nKey.SCIENCE$METHOD)}
          <select
            value={input.method}
            onChange={(event) => patch("method", event.target.value)}
          >
            {app.methods.map((method) => (
              <option key={method}>{method}</option>
            ))}
          </select>
        </label>
        {app.bases.length > 0 && (
          <label>
            {t(I18nKey.SCIENCE$BASIS)}
            <select
              value={input.basis}
              disabled={input.method === "r2SCAN-3c"}
              onChange={(event) => patch("basis", event.target.value)}
            >
              {app.bases.map((basis) => (
                <option key={basis}>{basis}</option>
              ))}
            </select>
          </label>
        )}
        {isMagus && (
          <>
            <label>
              {t(I18nKey.SCIENCE$MODEL_SIZE)}
              <select
                value={input.model_size}
                onChange={(event) =>
                  patch(
                    "model_size",
                    event.target.value as ScienceJobRequest["model_size"],
                  )
                }
              >
                {OFF23_MODEL_SIZES.map((size) => (
                  <option key={size} value={size}>
                    {size}
                  </option>
                ))}
              </select>
            </label>
            {SEARCH_FIELDS.map((field) => (
              <label key={field.key}>
                {t(field.label)}
                <input
                  type="number"
                  required
                  min={field.min}
                  max={field.max}
                  value={input[field.key]}
                  onChange={(event) =>
                    patch(field.key, Number(event.target.value))
                  }
                />
              </label>
            ))}
          </>
        )}
        {!isMagus && (
          <>
            <label>
              {t(I18nKey.SCIENCE$CHARGE)}
              <input
                type="number"
                min={-10}
                max={10}
                required
                value={input.charge}
                onChange={(event) =>
                  patch("charge", Number(event.target.value))
                }
              />
            </label>
            <label>
              {t(I18nKey.SCIENCE$MULTIPLICITY)}
              <input
                type="number"
                min={1}
                max={5}
                required
                value={input.multiplicity}
                onChange={(event) =>
                  patch("multiplicity", Number(event.target.value))
                }
              />
            </label>
          </>
        )}
        <label>
          {t(I18nKey.SCIENCE$CORES)}
          <input
            type="number"
            min={1}
            max={app.max_cores}
            required
            value={input.cores}
            onChange={(event) => patch("cores", Number(event.target.value))}
          />
        </label>
        <label>
          {t(I18nKey.SCIENCE$MEMORY)}
          <input
            type="number"
            min={512}
            max={app.max_memory_mb}
            step={256}
            required
            value={input.memory_mb}
            onChange={(event) => patch("memory_mb", Number(event.target.value))}
          />
        </label>
      </div>
      <p className="em-science-help">
        {t(
          isMagus
            ? I18nKey.SCIENCE$MAGUS_RESOURCE_NOTE
            : I18nKey.SCIENCE$RESOURCE_NOTE,
        )}
      </p>
      <ErrorMessage error={submit.error} />
      <BrandButton
        type="submit"
        variant="primary"
        testId="science-submit"
        isDisabled={
          !app.available || !input.xyz.trim() || fileError || submit.isPending
        }
        aria-busy={submit.isPending}
        startContent={<Play size={15} />}
      >
        {t(
          submit.isPending
            ? I18nKey.SCIENCE$SUBMITTING
            : I18nKey.SCIENCE$SUBMIT,
        )}
      </BrandButton>
    </form>
  );
}

function JobResult({ jobId }: { jobId: string | null }) {
  const { t } = useTranslation("openhands");
  const queryClient = useQueryClient();
  const [downloadError, setDownloadError] = useState<unknown>(null);
  const detail = useQuery({
    queryKey: SCIENCE_QUERY_KEYS.job(jobId),
    queryFn: () => scienceAppsService.job(jobId!),
    enabled: !!jobId,
    retry: false,
    refetchInterval: (query) =>
      isActive(query.state.data?.status) ? 1500 : false,
  });
  const cancel = useMutation({
    mutationFn: scienceAppsService.cancel,
    onSuccess: (job) => {
      queryClient.setQueryData(SCIENCE_QUERY_KEYS.job(job.id), job);
      void queryClient.invalidateQueries({ queryKey: SCIENCE_QUERY_KEYS.jobs });
    },
  });
  const job = detail.data;
  return (
    <section
      className="em-science-panel em-science-result"
      data-testid="science-job-result"
    >
      <div className="em-science-section-heading">
        <h2>{t(I18nKey.SCIENCE$RESULTS)}</h2>
        {job && (
          <span
            role="status"
            className="em-science-status"
            data-status={job.status}
          >
            {t(STATUS_KEYS[job.status])}
          </span>
        )}
      </div>
      {!jobId && (
        <div className="em-science-result-empty">
          <FlaskConical size={38} />
          <h3>{t(I18nKey.SCIENCE$READY_TITLE)}</h3>
          <p>{t(I18nKey.SCIENCE$READY_DESCRIPTION)}</p>
        </div>
      )}
      <ErrorMessage error={detail.error || cancel.error || downloadError} />
      {detail.isError && (
        <BrandButton
          type="button"
          variant="secondary"
          onClick={() => {
            void detail.refetch();
          }}
        >
          {t(I18nKey.SCIENCE$RETRY)}
        </BrandButton>
      )}
      {jobId && detail.isPending && (
        <p role="status">{t(I18nKey.SCIENCE$LOADING)}</p>
      )}
      {job && (
        <>
          <h3>{job.title}</h3>
          <p className="em-science-help">
            {new Date(job.created_at).toLocaleString()}
          </p>
          {isActive(job.status) && (
            <BrandButton
              type="button"
              variant="secondary"
              isDisabled={cancel.isPending}
              onClick={() => cancel.mutate(job.id)}
              startContent={<Square size={13} />}
            >
              {t(I18nKey.SCIENCE$STOP)}
            </BrandButton>
          )}
          {job.error && (
            <p className="em-science-error" role="alert">
              {t(ERROR_KEYS[job.error] ?? I18nKey.SCIENCE$CALCULATION_FAILED)}
            </p>
          )}
          {job.status === "succeeded" && (
            <div className="em-science-success">
              <Check size={16} />
              {t(I18nKey.SCIENCE$COMPLETED)}
            </div>
          )}
          {job.energy_hartree !== null && (
            <div className="em-science-energy">
              <span>{t(I18nKey.SCIENCE$FINAL_ENERGY)}</span>
              <strong>
                {t(I18nKey.SCIENCE$ENERGY_VALUE, {
                  value: job.energy_hartree.toFixed(8),
                })}
              </strong>
            </div>
          )}
          {job.energy_ev != null && (
            <div className="em-science-energy">
              <span>{t(I18nKey.SCIENCE$LOWEST_ENERGY)}</span>
              <strong>
                {t(I18nKey.SCIENCE$ENERGY_EV_VALUE, {
                  value: job.energy_ev.toFixed(8),
                })}
              </strong>
            </div>
          )}
          {job.app_id === "magus" && job.status === "succeeded" && (
            <p className="em-science-help">
              {t(I18nKey.SCIENCE$MAGUS_RESULT_NOTE)}
            </p>
          )}
          {job.status === "succeeded" && job.result?.route_count != null && (
            <>
              <p className="em-science-success">
                {t(I18nKey.SCIENCE$ROUTE_COUNTS, {
                  count: job.result.route_count,
                  solved: job.result.solved_count,
                })}
              </p>
              <p className="em-science-help">
                {t(I18nKey.SCIENCE$ROUTE_RESULT_NOTE)}
              </p>
            </>
          )}
          {job.status === "succeeded" && job.result?.correction_factors && (
            <>
              <h3>{t(I18nKey.SCIENCE$CF_VALUES)}</h3>
              {job.result.correction_factors.map((row, index) => (
                <div
                  key={`${index}-${row.smiles}`}
                  className="em-science-energy"
                >
                  <span className="break-all">{row.smiles}</span>
                  <strong>{row.cf.toFixed(6)}</strong>
                </div>
              ))}
              <p className="em-science-help">
                {t(I18nKey.SCIENCE$CF_RESULT_NOTE)}
              </p>
            </>
          )}
          <h3>{t(I18nKey.SCIENCE$LOG)}</h3>
          <textarea
            className="em-science-log"
            readOnly
            rows={12}
            aria-label={t(I18nKey.SCIENCE$LOG)}
            value={job.log || t(I18nKey.SCIENCE$WAITING_LOG)}
          />
          <h3>{t(I18nKey.SCIENCE$FILES)}</h3>
          <div className="em-science-file-list">
            {job.files.map((file) => (
              <button
                key={file.name}
                type="button"
                onClick={async () => {
                  try {
                    await scienceAppsService.download(job.id, file.name);
                    setDownloadError(null);
                  } catch (error) {
                    setDownloadError(error);
                  }
                }}
              >
                <Download size={14} />
                <span>{file.name}</span>
                <small>
                  {t(I18nKey.SCIENCE$FILE_SIZE, {
                    value: Math.max(1, Math.ceil(file.size / 1024)),
                  })}
                </small>
              </button>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
