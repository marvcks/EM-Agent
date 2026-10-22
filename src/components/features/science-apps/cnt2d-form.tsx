import { useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Play, Upload } from "lucide-react";
import { I18nKey } from "#/i18n/declaration";
import { BrandButton } from "#/components/features/settings/brand-button";
import { SCIENCE_QUERY_KEYS } from "#/hooks/query/query-keys";
import {
  scienceAppsService,
  SCIENCE_CNT_DEFAULTS,
  type ScienceApplication,
  type ScienceCNTParameters,
  type ScienceJob,
} from "#/api/science-apps-service";

const FIELDS = [
  ["box_size", I18nKey.SCIENCE$CNT_BOX],
  ["cnt_length", I18nKey.SCIENCE$CNT_LENGTH],
  ["cnt_width", I18nKey.SCIENCE$CNT_WIDTH],
  ["surface_width", I18nKey.SCIENCE$CNT_INTERFACE],
  ["filler_area_fraction_target", I18nKey.SCIENCE$CNT_FRACTION],
  ["angle_min", I18nKey.SCIENCE$CNT_ANGLE_MIN],
  ["angle_max", I18nKey.SCIENCE$CNT_ANGLE_MAX],
  ["cnt_k", I18nKey.SCIENCE$CNT_CORE_K],
  ["surface_k", I18nKey.SCIENCE$CNT_INTERFACE_K],
  ["pvdf_k", I18nKey.SCIENCE$CNT_MATRIX_K],
  ["t_left", I18nKey.SCIENCE$CNT_LEFT],
  ["t_right", I18nKey.SCIENCE$CNT_RIGHT],
  ["bulk_size", I18nKey.SCIENCE$CNT_BULK],
  ["interface_layers", I18nKey.SCIENCE$CNT_LAYERS],
] as const;
const UNITS = ["m", "cm", "mm", "um", "nm"] as const;

// @spec CNT2D-005 — Scientific parameters and optional archived geometry, without an LLM.
export function CNT2DForm({
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
  const [parameters, setParameters] = useState<ScienceCNTParameters>({
    ...SCIENCE_CNT_DEFAULTS,
  });
  const [corners, setCorners] = useState("");
  const [seed, setSeed] = useState(20260901);
  const [title, setTitle] = useState("");
  const [cores, setCores] = useState(2);
  const [memory, setMemory] = useState(4096);
  const [fileError, setFileError] = useState(false);
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
          app_id: "cnt2d",
          task: "conduction",
          method: "FEM-P2",
          basis: "",
          xyz: "",
          charge: 0,
          multiplicity: 1,
          title,
          cores,
          memory_mb: memory,
          cnt_parameters: parameters,
          cnt_corners: corners,
          cnt_seed: seed,
        });
      }}
    >
      <h2>{t(I18nKey.SCIENCE$PARAMETERS)}</h2>
      <p className="em-science-help">{t(I18nKey.SCIENCE$CNT_SCOPE)}</p>
      <label>
        {t(I18nKey.SCIENCE$JOB_TITLE)}
        <input
          value={title}
          maxLength={80}
          placeholder={app.name}
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>
      <div className="em-science-section-heading">
        <h3>{t(I18nKey.SCIENCE$CNT_PARAMETERS)}</h3>
        <button
          type="button"
          onClick={() => {
            setParameters({ ...SCIENCE_CNT_DEFAULTS });
            setSeed(20260901);
            setCorners("");
            setFileError(false);
          }}
        >
          {t(I18nKey.SCIENCE$CNT_EXAMPLE)}
        </button>
      </div>
      <label>
        {t(I18nKey.SCIENCE$CNT_UNIT_LENGTH)}
        <select
          value={parameters.length_unit}
          onChange={(event) =>
            setParameters((current) => ({
              ...current,
              length_unit: event.target
                .value as ScienceCNTParameters["length_unit"],
            }))
          }
        >
          {UNITS.map((unit) => (
            <option key={unit} value={unit}>
              {unit}
            </option>
          ))}
        </select>
      </label>
      <div className="em-science-fields">
        {FIELDS.map(([key, label]) => (
          <label key={key}>
            {t(label)}
            <input
              type="number"
              required
              step={key === "interface_layers" ? 1 : "any"}
              value={parameters[key]}
              onChange={(event) =>
                setParameters((current) => ({
                  ...current,
                  [key]: Number(event.target.value),
                }))
              }
            />
          </label>
        ))}
        <label>
          {t(I18nKey.SCIENCE$CNT_SEED)}
          <input
            type="number"
            required
            min={0}
            max={2147483647}
            step={1}
            value={seed}
            onChange={(event) => setSeed(Number(event.target.value))}
          />
        </label>
        <label>
          {t(I18nKey.SCIENCE$CORES)}
          <input
            type="number"
            required
            min={1}
            max={8}
            value={cores}
            onChange={(event) => setCores(Number(event.target.value))}
          />
        </label>
        <label>
          {t(I18nKey.SCIENCE$MEMORY)}
          <input
            type="number"
            required
            min={512}
            max={8192}
            step={512}
            value={memory}
            onChange={(event) => setMemory(Number(event.target.value))}
          />
        </label>
      </div>
      <p className="em-science-help">{t(I18nKey.SCIENCE$CNT_LIMITS)}</p>
      <label className="em-science-upload">
        <Upload size={18} />
        <span>{t(I18nKey.SCIENCE$CNT_UPLOAD)}</span>
        <input
          type="file"
          accept=".txt,.tsv"
          aria-label={t(I18nKey.SCIENCE$CNT_UPLOAD)}
          onChange={async (event) => {
            const file = event.target.files?.[0];
            if (!file) return;
            if (file.size > 32768 || !/\.(txt|tsv)$/i.test(file.name)) {
              setFileError(true);
              setCorners("");
              return;
            }
            try {
              setCorners(await file.text());
              setFileError(false);
            } catch {
              setFileError(true);
              setCorners("");
            }
          }}
        />
      </label>
      <label>
        {t(I18nKey.SCIENCE$CNT_CORNERS)}
        <textarea
          rows={5}
          maxLength={32768}
          value={corners}
          onChange={(event) => {
            setCorners(event.target.value);
            setFileError(false);
          }}
        />
      </label>
      <p className="em-science-help">{t(I18nKey.SCIENCE$CNT_CORNERS_HELP)}</p>
      {fileError && (
        <p className="em-science-error" role="alert">
          {t(I18nKey.SCIENCE$CNT_ERROR)}
        </p>
      )}
      {renderError(submit.error)}
      <BrandButton
        type="submit"
        variant="primary"
        testId="science-submit"
        isDisabled={!app.available || fileError || submit.isPending}
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

// @spec CNT2D-006 — Report conductivity and mesh evidence without claiming convergence.
export function CNT2DResult({
  result,
}: {
  result: NonNullable<ScienceJob["result"]>;
}) {
  const { t } = useTranslation("openhands");
  const m = result.metrics;
  if (!m) return null;
  return (
    <>
      <div className="em-science-energy">
        <span>{t(I18nKey.SCIENCE$CNT_KEFF)}</span>
        <strong>
          {m.Keff_X.toFixed(8)} <span>{t(I18nKey.SCIENCE$CNT_UNIT)}</span>
        </strong>
      </div>
      <div className="em-science-energy">
        <span>{t(I18nKey.SCIENCE$CNT_COUNT)}</span>
        <strong>{m.CNT_Number}</strong>
      </div>
      <div className="em-science-energy">
        <span>{t(I18nKey.SCIENCE$CNT_TRIANGLES)}</span>
        <strong>{m.Triangles}</strong>
      </div>
      <div className="em-science-energy">
        <span>{t(I18nKey.SCIENCE$CNT_BALANCE)}</span>
        <strong>{(100 * m.Energy_Balance_Error).toExponential(3)}</strong>
      </div>
      <p className="em-science-help">{t(I18nKey.SCIENCE$CNT_RESULT_NOTE)}</p>
    </>
  );
}
