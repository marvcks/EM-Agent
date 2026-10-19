import { useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Play, Upload } from "lucide-react";
import { I18nKey } from "#/i18n/declaration";
import { BrandButton } from "#/components/features/settings/brand-button";
import { SCIENCE_QUERY_KEYS } from "#/hooks/query/query-keys";
import {
  scienceAppsService,
  SCIENCE_ROUTE_EXAMPLE,
  SCIENCE_CF_EXAMPLE,
  type ScienceApplication,
  type ScienceJobRequest,
} from "#/api/science-apps-service";

const ROUTE_FIELDS = [
  {
    key: "iterations",
    label: I18nKey.SCIENCE$SEARCH_ITERATIONS,
    min: 1,
    max: 500,
  },
  {
    key: "search_seconds",
    label: I18nKey.SCIENCE$SEARCH_SECONDS,
    min: 1,
    max: 600,
  },
  {
    key: "max_transforms",
    label: I18nKey.SCIENCE$SEARCH_DEPTH,
    min: 1,
    max: 10,
  },
  { key: "max_routes", label: I18nKey.SCIENCE$MAX_ROUTES, min: 1, max: 25 },
] as const;

export function ReactionForm({
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
  const isRoute = app.id === "aizynthfinder";
  const [input, setInput] = useState<ScienceJobRequest>({
    app_id: app.id,
    xyz: "",
    smiles: "",
    title: "",
    task: isRoute ? "retrosynthesis" : "correction_factor",
    method: app.methods[0],
    basis: "",
    charge: 0,
    multiplicity: 1,
    cores: 2,
    memory_mb: isRoute ? 6144 : 2048,
    ...(isRoute
      ? {
          iterations: 100,
          search_seconds: 60,
          max_transforms: 6,
          max_routes: 10,
        }
      : {}),
  });
  const [fileError, setFileError] = useState(false);
  const patch = <K extends keyof ScienceJobRequest>(
    key: K,
    value: ScienceJobRequest[K],
  ) => setInput((current) => ({ ...current, [key]: value }));
  const submit = useMutation({
    mutationFn: scienceAppsService.submit,
    onSuccess: (job) => {
      void client.invalidateQueries({ queryKey: SCIENCE_QUERY_KEYS.jobs });
      onCreated(job.id);
    },
  });
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
        <h3>{t(I18nKey.SCIENCE$SMILES_INPUT)}</h3>
        <button
          type="button"
          onClick={() => {
            patch(
              "smiles",
              isRoute ? SCIENCE_ROUTE_EXAMPLE : SCIENCE_CF_EXAMPLE,
            );
            setFileError(false);
          }}
        >
          {t(I18nKey.SCIENCE$SMILES_EXAMPLE)}
        </button>
      </div>
      <label className="em-science-upload">
        <Upload size={18} />
        <span>{t(I18nKey.SCIENCE$UPLOAD_SMILES)}</span>
        <input
          type="file"
          accept=".smi,.txt"
          aria-label={t(I18nKey.SCIENCE$UPLOAD_SMILES)}
          onChange={async (event) => {
            const file = event.target.files?.[0];
            if (!file) return;
            if (file.size > 32768 || !/\.(smi|txt)$/i.test(file.name)) {
              setFileError(true);
              return;
            }
            try {
              patch("smiles", await file.text());
              setFileError(false);
            } catch {
              setFileError(true);
            }
          }}
        />
      </label>
      {fileError && (
        <p role="alert" className="em-science-error">
          {t(I18nKey.SCIENCE$SMILES_FILE_ERROR)}
        </p>
      )}
      <label>
        {t(I18nKey.SCIENCE$SMILES_INPUT)}
        <textarea
          required
          rows={5}
          maxLength={32768}
          value={input.smiles}
          onChange={(event) => {
            patch("smiles", event.target.value);
            setFileError(false);
          }}
        />
      </label>
      <p className="em-science-help">
        {t(
          isRoute
            ? I18nKey.SCIENCE$ROUTE_INPUT_HELP
            : I18nKey.SCIENCE$CF_INPUT_HELP,
        )}
      </p>
      <div className="em-science-fields">
        {isRoute &&
          ROUTE_FIELDS.map((field) => (
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
          !input.smiles?.trim() ||
          fileError ||
          submit.isPending
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
