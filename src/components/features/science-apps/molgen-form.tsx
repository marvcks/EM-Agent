import { useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Play } from "lucide-react";
import { I18nKey } from "#/i18n/declaration";
import { BrandButton } from "#/components/features/settings/brand-button";
import { SCIENCE_QUERY_KEYS } from "#/hooks/query/query-keys";
import {
  scienceAppsService,
  type ScienceApplication,
  type ScienceJob,
  type ScienceJobRequest,
} from "#/api/science-apps-service";

const MOLGEN_FIELDS = [
  {
    key: "molgen_workers",
    label: I18nKey.SCIENCE$MOLGEN_WORKERS,
    min: 1,
    max: 7,
  },
  {
    key: "molgen_seconds",
    label: I18nKey.SCIENCE$MOLGEN_SECONDS,
    min: 60,
    max: 720,
  },
  {
    key: "molgen_seed",
    label: I18nKey.SCIENCE$MOLGEN_SEED,
    min: 0,
    max: 2147483647,
  },
] as const;

export function MolgenForm({
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
    app_id: app.id,
    xyz: "",
    smiles: "",
    title: "",
    task: "generation",
    method: "ChemTSv3",
    basis: "",
    charge: 0,
    multiplicity: 1,
    cores: 3,
    memory_mb: 4096,
    molgen_workers: 2,
    molgen_seconds: 600,
    molgen_seed: 20261030,
  });
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
        submit.mutate({
          ...input,
          cores: (input.molgen_workers ?? 2) + 1,
        });
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
      <p className="em-science-help">{t(I18nKey.SCIENCE$MOLGEN_INPUT_HELP)}</p>
      <div className="em-science-fields">
        {MOLGEN_FIELDS.map((field) => (
          <label key={field.key}>
            {t(field.label)}
            <input
              type="number"
              required
              min={field.min}
              max={field.max}
              value={input[field.key]}
              onChange={(event) => patch(field.key, Number(event.target.value))}
            />
          </label>
        ))}
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
        {t(I18nKey.SCIENCE$MOLGEN_RESOURCE_NOTE)}
      </p>
      <p className="em-science-help">{t(I18nKey.SCIENCE$MOLGEN_MANUAL_NOTE)}</p>
      {renderError(submit.error)}
      <BrandButton
        type="submit"
        variant="primary"
        testId="science-submit"
        isDisabled={!app.available || submit.isPending}
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

export function MolgenResult({
  result,
}: {
  result: NonNullable<ScienceJob["result"]>;
}) {
  const { t } = useTranslation("openhands");
  return (
    <>
      <p className="em-science-success">
        {t(I18nKey.SCIENCE$MOLGEN_COUNTS, {
          records: result.generated_records ?? 0,
          unique: result.unique_generated ?? 0,
          pool: result.generated_pool_rows ?? 0,
        })}
      </p>
      <h3>{t(I18nKey.SCIENCE$MOLGEN_TOP)}</h3>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead>
            <tr>
              <th>{t(I18nKey.SCIENCE$MOLGEN_SMILES)}</th>
              <th>{t(I18nKey.SCIENCE$MOLGEN_REWARD)}</th>
              <th>{t(I18nKey.SCIENCE$MOLGEN_DENSITY)}</th>
              <th>{t(I18nKey.SCIENCE$MOLGEN_BDE)}</th>
              <th>{t(I18nKey.SCIENCE$MOLGEN_TD)}</th>
            </tr>
          </thead>
          <tbody>
            {(result.top_molecules ?? []).map((row) => (
              <tr key={row.smiles}>
                <td className="break-all p-2">{row.smiles}</td>
                <td className="p-2">{row.reward.toFixed(3)}</td>
                <td className="p-2">{row.density?.toFixed(3) ?? "—"}</td>
                <td className="p-2">{row.BDE?.toFixed(1) ?? "—"}</td>
                <td className="p-2">{row.Td?.toFixed(1) ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="em-science-help">{t(I18nKey.SCIENCE$MOLGEN_RESULT_NOTE)}</p>
    </>
  );
}
