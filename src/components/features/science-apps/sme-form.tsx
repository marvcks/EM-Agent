import { useEffect, useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Play, Upload } from "lucide-react";
import { I18nKey } from "#/i18n/declaration";
import { BrandButton } from "#/components/features/settings/brand-button";
import { SCIENCE_QUERY_KEYS } from "#/hooks/query/query-keys";
import {
  scienceAppsService,
  SCIENCE_SME_EXAMPLE,
  SCIENCE_SME_FRAGMENTATIONS,
  SCIENCE_SME_TASKS,
  type ScienceApplication,
  type ScienceJobRequest,
  type ScienceJob,
  type ScienceSMEFragmentation,
  type ScienceSMEMolecule,
  type ScienceSMETask,
} from "#/api/science-apps-service";

const TASK_LABELS: Record<ScienceSMETask, I18nKey> = {
  DV_R: I18nKey.SCIENCE$SME_TASK_DV_R,
  Density_R: I18nKey.SCIENCE$SME_TASK_DENSITY_R,
  DV_C: I18nKey.SCIENCE$SME_TASK_DV_C,
  IS_R: I18nKey.SCIENCE$SME_TASK_IS_R,
  IS_C: I18nKey.SCIENCE$SME_TASK_IS_C,
  MP: I18nKey.SCIENCE$SME_TASK_MP,
  ESOL: I18nKey.SCIENCE$SME_TASK_ESOL,
};
const FRAGMENT_LABELS: Record<ScienceSMEFragmentation, I18nKey> = {
  all: I18nKey.SCIENCE$SME_ALL,
  brics: I18nKey.SCIENCE$SME_BRICS,
  murcko: I18nKey.SCIENCE$SME_MURCKO,
  fg: I18nKey.SCIENCE$SME_FG,
};
const SCHEME_LABELS: Record<string, I18nKey> = {
  brics: I18nKey.SCIENCE$SME_BRICS,
  murcko: I18nKey.SCIENCE$SME_MURCKO,
  fg: I18nKey.SCIENCE$SME_FG,
};

// @spec SME-002 — SMILES-only manual input shares the scientific queue
export function SMEForm({
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
    app_id: "sme",
    task: "prediction",
    xyz: "",
    title: "",
    method: "RGCN",
    basis: "",
    charge: 0,
    multiplicity: 1,
    cores: 2,
    memory_mb: 2048,
    smiles: "",
    input_kind: "smiles",
    sme_task: "DV_R",
    sme_fragmentation: "all",
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
        <h3>{t(I18nKey.SCIENCE$SME_INPUT)}</h3>
        <button
          type="button"
          onClick={() => {
            patch("smiles", SCIENCE_SME_EXAMPLE);
            setFileError(false);
          }}
        >
          {t(I18nKey.SCIENCE$SME_EXAMPLE)}
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
        <p className="em-science-error" role="alert">
          {t(I18nKey.SCIENCE$SMILES_FILE_ERROR)}
        </p>
      )}
      <label>
        <span className="sr-only">{t(I18nKey.SCIENCE$SME_INPUT)}</span>
        <textarea
          required
          rows={7}
          maxLength={32768}
          value={input.smiles}
          placeholder={t(I18nKey.SCIENCE$SME_PLACEHOLDER)}
          onChange={(event) => {
            patch("smiles", event.target.value);
            setFileError(false);
          }}
        />
      </label>
      <p className="em-science-help">{t(I18nKey.SCIENCE$SME_INPUT_HELP)}</p>
      <div className="em-science-fields">
        <label>
          {t(I18nKey.SCIENCE$SME_TASK)}
          <select
            value={input.sme_task}
            onChange={(event) =>
              patch("sme_task", event.target.value as ScienceSMETask)
            }
          >
            {SCIENCE_SME_TASKS.map((task) => (
              <option key={task} value={task}>
                {t(TASK_LABELS[task])}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t(I18nKey.SCIENCE$SME_FRAGMENTATION)}
          <select
            value={input.sme_fragmentation}
            onChange={(event) =>
              patch(
                "sme_fragmentation",
                event.target.value as ScienceSMEFragmentation,
              )
            }
          >
            {SCIENCE_SME_FRAGMENTATIONS.map((fragmentation) => (
              <option key={fragmentation} value={fragmentation}>
                {t(FRAGMENT_LABELS[fragmentation])}
              </option>
            ))}
          </select>
        </label>
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
      <p className="em-science-help">{t(I18nKey.SCIENCE$SME_SCOPE)}</p>
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
          !input.smiles?.trim()
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

function AttributionImage({ jobId, name }: { jobId: string; name: string }) {
  const { t } = useTranslation("openhands");
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    const revoke = (value: string) => {
      if (typeof URL.revokeObjectURL === "function") URL.revokeObjectURL(value);
    };
    let active = true;
    let objectUrl: string | null = null;
    scienceAppsService
      .preview(jobId, name)
      .then((value) => {
        if (active) {
          objectUrl = value;
          setUrl(value);
        } else {
          revoke(value);
        }
      })
      .catch(() => setUrl(null));
    return () => {
      active = false;
      if (objectUrl) revoke(objectUrl);
    };
  }, [jobId, name]);
  return (
    <figure>
      {url ? (
        <img src={url} alt={t(I18nKey.SCIENCE$SME_IMAGE)} />
      ) : (
        <figcaption>{name}</figcaption>
      )}
      <figcaption>{name.split(".")[0]}</figcaption>
    </figure>
  );
}

function MoleculeResult({
  jobId,
  molecule,
  kind,
}: {
  jobId: string;
  molecule: ScienceSMEMolecule;
  kind: "regression" | "classification";
}) {
  const { t } = useTranslation("openhands");
  return (
    <div className="em-science-sme-molecule">
      <h3>
        {t(I18nKey.SCIENCE$SME_MOLECULE)} {molecule.index}: {molecule.smiles}
      </h3>
      {kind === "classification" ? (
        <div className="em-science-energy">
          <span>{t(I18nKey.SCIENCE$SME_PROBABILITY)}</span>
          <strong>{(molecule.probability_class1 ?? 0).toPrecision(4)}</strong>
          <span>{t(I18nKey.SCIENCE$SME_LABEL)}</span>
          <strong>{molecule.label}</strong>
        </div>
      ) : (
        <div className="em-science-energy">
          <span>{t(I18nKey.SCIENCE$SME_PREDICTION)}</span>
          <strong>
            {molecule.prediction.mean.toPrecision(5)} ±{" "}
            {molecule.prediction.std.toPrecision(2)}
          </strong>
        </div>
      )}
      <div className="em-science-sme-images">
        {Object.entries(molecule.schemes).map(([scheme, entry]) => (
          <AttributionImage key={scheme} jobId={jobId} name={entry.image} />
        ))}
      </div>
      {Object.entries(molecule.schemes).map(([scheme, entry]) => (
        <div key={scheme} className="em-science-sme-fragment">
          <h3>{t(SCHEME_LABELS[scheme] ?? I18nKey.SCIENCE$SME_FRAGMENTS)}</h3>
          <div className="em-bde-table-scroll">
            <table className="em-bde-table">
              <thead>
                <tr>
                  <th>{t(I18nKey.SCIENCE$SME_FRAGMENT)}</th>
                  <th>{t(I18nKey.SCIENCE$SME_ATOMS)}</th>
                  <th>{t(I18nKey.SCIENCE$SME_ATTRIBUTION)}</th>
                  <th>{t(I18nKey.SCIENCE$SME_ATTRIBUTION_NORMALIZED)}</th>
                  <th>{t(I18nKey.SCIENCE$SME_MASKED)}</th>
                </tr>
              </thead>
              <tbody>
                {entry.fragments.map((fragment) => (
                  <tr key={fragment.index}>
                    <td className="break-all">{fragment.label}</td>
                    <td>{fragment.atom_count}</td>
                    <td>{fragment.attribution.toPrecision(4)}</td>
                    <td>{fragment.attribution_normalized.toFixed(3)}</td>
                    <td>{fragment.masked_prediction_mean.toPrecision(5)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </div>
  );
}

// @spec SME-004 — Per-molecule predictions with fragment attribution images
export function SMEResult({
  jobId,
  result,
}: {
  jobId: string;
  result: NonNullable<ScienceJob["result"]>;
}) {
  const { t } = useTranslation("openhands");
  if (!result.molecules) return null;
  const kind = result.kind ?? "regression";
  const metric =
    kind === "classification"
      ? (result.ensemble_metrics?.accuracy ??
        result.model_metrics?.test_accuracy_mean)
      : (result.ensemble_metrics?.r2 ?? result.model_metrics?.test_r2_mean);
  return (
    <div className="em-bde-result">
      {kind === "classification" ? (
        <div className="em-science-energy">
          <span>{t(I18nKey.SCIENCE$SME_TEST_ACCURACY)}</span>
          <strong>
            {metric != null ? `${(metric * 100).toFixed(1)}%` : "—"}
          </strong>
        </div>
      ) : (
        <div className="em-science-energy">
          <span>{t(I18nKey.SCIENCE$SME_TEST_R2)}</span>
          <strong>{metric != null ? metric.toFixed(3) : "—"}</strong>
        </div>
      )}
      <div className="em-science-energy">
        <span>{t(I18nKey.SCIENCE$SME_SEED_COUNT)}</span>
        <strong>{result.seed_count}</strong>
      </div>
      <p className="em-science-help">{t(I18nKey.SCIENCE$SME_RESULT_NOTE)}</p>
      {result.molecules.map((molecule) => (
        <MoleculeResult
          key={molecule.index}
          jobId={jobId}
          molecule={molecule}
          kind={kind}
        />
      ))}
    </div>
  );
}
