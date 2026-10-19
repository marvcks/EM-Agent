import { useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { I18nKey } from "#/i18n/declaration";
import { BrandButton } from "#/components/features/settings/brand-button";
import { SCIENCE_QUERY_KEYS } from "#/hooks/query/query-keys";
import {
  scienceAppsService,
  type ScienceApplication,
  type ScienceJobRequest,
  type ScienceJob,
} from "#/api/science-apps-service";

// @spec BDE-001 — Manual BDE input uses the shared scientific queue
export function BDEForm({
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
    app_id: "bde",
    task: "bde",
    xyz: "",
    smiles: "",
    compound_name: "",
    input_kind: "smiles",
    method: "ALFABET",
    basis: "",
    title: "",
    charge: 0,
    multiplicity: 1,
    cores: 2,
    memory_mb: 4096,
  });
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
          value={input.title}
          maxLength={80}
          onChange={(event) => patch("title", event.target.value)}
        />
      </label>
      <label>
        {t(I18nKey.SCIENCE$BDE_MODE)}
        <select
          value={input.method}
          onChange={(event) => patch("method", event.target.value)}
        >
          <option value="ALFABET">{t(I18nKey.SCIENCE$BDE_ML)}</option>
          <option value="Psi4">{t(I18nKey.SCIENCE$BDE_PSI4)}</option>
        </select>
      </label>
      <label>
        {t(I18nKey.SCIENCE$BDE_INPUT_KIND)}
        <select
          value={input.input_kind}
          onChange={(event) =>
            setInput((current) => ({
              ...current,
              input_kind: event.target.value as "smiles" | "name",
              smiles: "",
              compound_name: "",
            }))
          }
        >
          <option value="smiles">{t(I18nKey.SCIENCE$SMILES_INPUT)}</option>
          <option value="name">{t(I18nKey.SCIENCE$BDE_NAME)}</option>
        </select>
      </label>
      {input.input_kind === "name" ? (
        <label>
          {t(I18nKey.SCIENCE$BDE_NAME)}
          <input
            required
            maxLength={256}
            value={input.compound_name}
            onChange={(event) => patch("compound_name", event.target.value)}
          />
        </label>
      ) : (
        <label>
          {t(I18nKey.SCIENCE$SMILES_INPUT)}
          <textarea
            required
            rows={3}
            maxLength={4096}
            value={input.smiles}
            onChange={(event) => patch("smiles", event.target.value)}
          />
        </label>
      )}
      <button
        type="button"
        onClick={() =>
          setInput((current) => ({
            ...current,
            smiles: current.input_kind === "smiles" ? "CCO" : "",
            compound_name: current.input_kind === "name" ? "ethanol" : "",
          }))
        }
      >
        {t(I18nKey.SCIENCE$SMILES_EXAMPLE)}
      </button>
      <p className="em-science-help">{t(I18nKey.SCIENCE$BDE_SCOPE)}</p>
      <p className="em-science-help">
        {t(
          input.method === "Psi4"
            ? I18nKey.SCIENCE$BDE_QM_NOTE
            : I18nKey.SCIENCE$BDE_ML_NOTE,
        )}
      </p>
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
      {renderError(submit.error)}
      <BrandButton
        type="submit"
        variant="primary"
        testId="science-submit"
        isDisabled={
          !app.available ||
          submit.isPending ||
          !(input.input_kind === "name"
            ? input.compound_name?.trim()
            : input.smiles?.trim())
        }
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

const REASON_KEYS: Record<string, I18nKey> = {
  ring_bond: I18nKey.SCIENCE$BDE_RING,
  multiple_bond: I18nKey.SCIENCE$BDE_MULTIPLE,
  unsupported_radicals: I18nKey.SCIENCE$BDE_UNSUPPORTED,
};
// @spec BDE-004 — Numbered graph, per-bond values and supported minimum
export function BDEResult({
  result,
}: {
  result: NonNullable<ScienceJob["result"]>;
}) {
  const { t } = useTranslation("openhands");
  if (!result.bonds) return null;
  return (
    <div className="em-bde-result">
      <h3>{t(I18nKey.SCIENCE$BDE_GRAPH)}</h3>
      <p className="em-science-help break-all">{result.canonical_smiles}</p>
      {result.diagram_png_base64 && (
        <img
          src={`data:image/png;base64,${result.diagram_png_base64}`}
          alt={t(I18nKey.SCIENCE$BDE_GRAPH)}
          className="em-bde-graph"
        />
      )}
      <div className="em-science-energy">
        <span>{t(I18nKey.SCIENCE$BDE_MINIMUM)}</span>
        <strong>
          {t(I18nKey.SCIENCE$BDE_MIN_VALUE, {
            bond: result.minimum_bond_index,
            value: result.minimum_bde_kcal_mol?.toFixed(2),
          })}
        </strong>
      </div>
      <p className="em-science-help">{t(I18nKey.SCIENCE$BDE_RESULT_NOTE)}</p>
      <p className="em-science-help">
        {t(
          result.mode === "Psi4"
            ? I18nKey.SCIENCE$BDE_QM_NOTE
            : I18nKey.SCIENCE$BDE_ML_NOTE,
        )}
      </p>
      <div className="em-bde-table-scroll">
        <table className="em-bde-table">
          <caption>{t(I18nKey.SCIENCE$BDE_TABLE)}</caption>
          <thead>
            <tr>
              <th>{t(I18nKey.SCIENCE$BDE_BOND)}</th>
              <th>{t(I18nKey.SCIENCE$BDE_VALUE)}</th>
              <th>{t(I18nKey.SCIENCE$BDE_FRAGMENTS)}</th>
            </tr>
          </thead>
          <tbody>
            {result.bonds.map((row) => (
              <tr
                key={row.bond_index}
                data-minimum={row.bond_index === result.minimum_bond_index}
              >
                <td>
                  {t(I18nKey.SCIENCE$BDE_BOND_VALUE, {
                    bond: row.bond_index,
                    a: row.atom1,
                    b: row.atom2,
                    type: row.bond_type,
                  })}
                </td>
                <td>
                  {row.status === "ok"
                    ? row.bde_kcal_mol?.toFixed(2)
                    : t(
                        REASON_KEYS[row.reason] ??
                          I18nKey.SCIENCE$BDE_UNSUPPORTED,
                      )}
                </td>
                <td className="break-all">{row.fragments.join(" + ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
