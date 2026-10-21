import { useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Play, Upload } from "lucide-react";
import { I18nKey } from "#/i18n/declaration";
import { BrandButton } from "#/components/features/settings/brand-button";
import { SCIENCE_QUERY_KEYS } from "#/hooks/query/query-keys";
import {
  scienceAppsService,
  SCIENCE_MORPHOLOGY_EXAMPLE_CSV,
  SCIENCE_MORPHOLOGY_FEATURES,
  type ScienceApplication,
  type ScienceJobRequest,
  type ScienceJob,
} from "#/api/science-apps-service";

const FEATURE_FIELDS = [
  {
    key: "additive_percent",
    label: I18nKey.SCIENCE$MORPHOLOGY_ADDITIVE,
    min: 0,
    max: 20,
    step: 0.1,
    example: 1,
  },
  {
    key: "antisolvent_temp_c",
    label: I18nKey.SCIENCE$MORPHOLOGY_TEMP,
    min: -10,
    max: 60,
    step: 1,
    example: 10,
  },
  {
    key: "stirring_rpm",
    label: I18nKey.SCIENCE$MORPHOLOGY_RPM,
    min: 50,
    max: 2000,
    step: 50,
    example: 300,
  },
  {
    key: "concentration_g_ml",
    label: I18nKey.SCIENCE$MORPHOLOGY_CONCENTRATION,
    min: 0.001,
    max: 0.5,
    step: 0.001,
    example: 0.06,
  },
  {
    key: "solvent_ratio",
    label: I18nKey.SCIENCE$MORPHOLOGY_RATIO,
    min: 0.001,
    max: 2,
    step: 0.001,
    example: 0.125,
  },
] as const;
const MODEL_OPTIONS = [
  "auto",
  "CatBoost",
  "LightGBM",
  "XGBoost",
  "SVM",
  "GradientBoosting",
  "RandomForest",
];

// @spec CM-001 — Manual morphology input shares the scientific queue
export function MorphologyForm({
  app,
  onCreated,
  renderError,
}: {
  app: ScienceApplication;
  onCreated: (id: string) => void;
  renderError: (error: unknown) => ReactNode;
}) {
  const { t } = useTranslation("openhands");
  const client = useQueryClient();
  const [input, setInput] = useState<ScienceJobRequest>({
    app_id: "crystal-morphology",
    task: "classification",
    xyz: "",
    title: "",
    method: "auto",
    basis: "",
    charge: 0,
    multiplicity: 1,
    cores: 2,
    memory_mb: 2048,
    input_mode: "single",
    table_csv: "",
    additive_percent: 1,
    antisolvent_temp_c: 10,
    stirring_rpm: 300,
    concentration_g_ml: 0.06,
    solvent_ratio: 0.125,
  });
  const [fileError, setFileError] = useState(false);
  const submit = useMutation({
    mutationFn: scienceAppsService.submit,
    onSuccess: (job) => {
      void client.invalidateQueries({ queryKey: SCIENCE_QUERY_KEYS.jobs });
      onCreated(job.id);
    },
  });
  const patch = <K extends keyof ScienceJobRequest>(
    key: K,
    value: ScienceJobRequest[K],
  ) => setInput((current) => ({ ...current, [key]: value }));
  const isBatch = input.input_mode === "batch";
  // The service validates modes strictly: batch requests carry only the CSV,
  // single requests only the five parameters.
  const payload = (): ScienceJobRequest =>
    isBatch
      ? {
          ...input,
          additive_percent: undefined,
          antisolvent_temp_c: undefined,
          stirring_rpm: undefined,
          concentration_g_ml: undefined,
          solvent_ratio: undefined,
        }
      : { ...input, table_csv: "" };
  return (
    <form
      className="em-science-panel em-science-form"
      onSubmit={(event) => {
        event.preventDefault();
        submit.mutate(payload());
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
      <label>
        {t(I18nKey.SCIENCE$MORPHOLOGY_INPUT_MODE)}
        <select
          value={input.input_mode}
          onChange={(event) =>
            patch("input_mode", event.target.value as "single" | "batch")
          }
        >
          <option value="single">{t(I18nKey.SCIENCE$MORPHOLOGY_SINGLE)}</option>
          <option value="batch">{t(I18nKey.SCIENCE$MORPHOLOGY_BATCH)}</option>
        </select>
      </label>
      <label>
        {t(I18nKey.SCIENCE$MORPHOLOGY_MODEL)}
        <select
          value={input.method}
          onChange={(event) => patch("method", event.target.value)}
        >
          {MODEL_OPTIONS.map((model) => (
            <option key={model} value={model}>
              {model === "auto" ? t(I18nKey.SCIENCE$MORPHOLOGY_AUTO) : model}
            </option>
          ))}
        </select>
      </label>
      {isBatch ? (
        <>
          <div className="em-science-section-heading">
            <h3>{t(I18nKey.SCIENCE$MORPHOLOGY_BATCH)}</h3>
            <button
              type="button"
              onClick={() => {
                patch("table_csv", SCIENCE_MORPHOLOGY_EXAMPLE_CSV);
                setFileError(false);
              }}
            >
              {t(I18nKey.SCIENCE$MORPHOLOGY_CSV_EXAMPLE)}
            </button>
          </div>
          <label className="em-science-upload">
            <Upload size={18} />
            <span>{t(I18nKey.SCIENCE$MORPHOLOGY_UPLOAD_CSV)}</span>
            <input
              type="file"
              accept=".csv,.txt"
              aria-label={t(I18nKey.SCIENCE$MORPHOLOGY_UPLOAD_CSV)}
              onChange={async (event) => {
                const file = event.target.files?.[0];
                if (!file) return;
                if (file.size > 32768 || !/\.(csv|txt)$/i.test(file.name)) {
                  setFileError(true);
                  return;
                }
                try {
                  patch("table_csv", await file.text());
                  setFileError(false);
                } catch {
                  setFileError(true);
                }
              }}
            />
          </label>
          {fileError && (
            <p className="em-science-error" role="alert">
              {t(I18nKey.SCIENCE$MORPHOLOGY_FILE_ERROR)}
            </p>
          )}
          <label>
            <span className="sr-only">
              {t(I18nKey.SCIENCE$MORPHOLOGY_BATCH)}
            </span>
            <textarea
              required
              rows={7}
              maxLength={32768}
              value={input.table_csv}
              placeholder={t(I18nKey.SCIENCE$MORPHOLOGY_CSV_PLACEHOLDER)}
              onChange={(event) => {
                patch("table_csv", event.target.value);
                setFileError(false);
              }}
            />
          </label>
          <p className="em-science-help">
            {t(I18nKey.SCIENCE$MORPHOLOGY_BATCH_HELP)}
          </p>
        </>
      ) : (
        <div className="em-science-fields">
          {FEATURE_FIELDS.map((field) => (
            <label key={field.key}>
              {t(field.label)}
              <input
                type="number"
                required
                min={field.min}
                max={field.max}
                step={field.step}
                value={input[field.key]}
                onChange={(event) =>
                  patch(field.key, Number(event.target.value))
                }
              />
            </label>
          ))}
        </div>
      )}
      <p className="em-science-help">{t(I18nKey.SCIENCE$MORPHOLOGY_SCOPE)}</p>
      <div className="em-science-fields">
        <label>
          {t(I18nKey.SCIENCE$CORES)}
          <input
            type="number"
            required
            min={1}
            max={app.max_cores}
            value={input.cores}
            onChange={(event) => patch("cores", Number(event.target.value))}
          />
        </label>
        <label>
          {t(I18nKey.SCIENCE$MEMORY)}
          <input
            type="number"
            required
            min={512}
            max={app.max_memory_mb}
            step={256}
            value={input.memory_mb}
            onChange={(event) => patch("memory_mb", Number(event.target.value))}
          />
        </label>
      </div>
      <p className="em-science-help">
        {t(I18nKey.SCIENCE$REACTION_RESOURCE_NOTE)}
      </p>
      {renderError(submit.error)}
      <BrandButton
        type="submit"
        variant="primary"
        testId="science-submit"
        isDisabled={
          !app.available ||
          submit.isPending ||
          fileError ||
          (isBatch ? !input.table_csv?.trim() : false)
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

// @spec CM-004 — Per-row classes with probabilities and envelope warnings
export function MorphologyResult({
  result,
}: {
  result: NonNullable<ScienceJob["result"]>;
}) {
  const { t } = useTranslation("openhands");
  if (!result.rows) return null;
  return (
    <div className="em-bde-result">
      <div className="em-science-energy">
        <span>{t(I18nKey.SCIENCE$MORPHOLOGY_MODEL)}</span>
        <strong>{result.model_id}</strong>
      </div>
      <p className="em-science-help">
        {t(I18nKey.SCIENCE$MORPHOLOGY_RESULT_NOTE)}
      </p>
      {result.class_counts && (
        <p className="em-science-success">
          {t(I18nKey.SCIENCE$MORPHOLOGY_COUNTS, {
            other: result.class_counts["其他"] ?? 0,
            spherical: result.class_counts["球"] ?? 0,
            needle: result.class_counts["针"] ?? 0,
          })}
        </p>
      )}
      {!!result.outside_training_range_count && (
        <p className="em-science-error" role="alert">
          {t(I18nKey.SCIENCE$MORPHOLOGY_OUTSIDE, {
            count: result.outside_training_range_count,
          })}
        </p>
      )}
      <div className="em-bde-table-scroll">
        <table className="em-bde-table">
          <caption>{t(I18nKey.SCIENCE$MORPHOLOGY_TABLE)}</caption>
          <thead>
            <tr>
              <th>{t(I18nKey.SCIENCE$MORPHOLOGY_ROW)}</th>
              {SCIENCE_MORPHOLOGY_FEATURES.map((feature) => (
                <th key={feature}>{feature}</th>
              ))}
              <th>{t(I18nKey.SCIENCE$MORPHOLOGY_PREDICTION)}</th>
              <th>{t(I18nKey.SCIENCE$MORPHOLOGY_RANGE)}</th>
              {Object.keys(result.rows[0].probabilities).map((label) => (
                <th key={label}>{`P(${label})`}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows.map((row) => (
              <tr
                key={row.index}
                data-minimum={
                  row.predicted_label === "球" && row.in_training_range
                }
              >
                <td>{row.index}</td>
                {SCIENCE_MORPHOLOGY_FEATURES.map((feature) => (
                  <td key={feature}>{row.features[feature]}</td>
                ))}
                <td>{row.predicted_label}</td>
                <td>
                  {t(
                    row.in_training_range
                      ? I18nKey.SCIENCE$MORPHOLOGY_IN_RANGE
                      : I18nKey.SCIENCE$MORPHOLOGY_EXTRAPOLATION,
                  )}
                </td>
                {Object.values(row.probabilities).map((value, index) => (
                  <td key={index}>{value.toFixed(3)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
