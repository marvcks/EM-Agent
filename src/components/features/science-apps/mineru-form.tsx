import { useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Play, Upload } from "lucide-react";
import { I18nKey } from "#/i18n/declaration";
import { BrandButton } from "#/components/features/settings/brand-button";
import { SCIENCE_QUERY_KEYS } from "#/hooks/query/query-keys";
import {
  scienceAppsService,
  MAX_SCIENCE_DOCUMENT_BYTES,
  type ScienceApplication,
  type ScienceDocumentOptions,
} from "#/api/science-apps-service";

// @spec MINERU-004 — PDF/Word form submits directly to the shared service
export function MinerUForm({
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
  const [file, setFile] = useState<File | null>(null);
  const [invalid, setInvalid] = useState(false);
  const [options, setOptions] = useState<ScienceDocumentOptions>({
    title: "",
    method: "vlm",
    language: "ch",
    enable_formula: true,
    enable_table: true,
  });
  const submit = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("missing_document");
      return scienceAppsService.submitDocument(file, options);
    },
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
        if (file && !invalid && app.available && !submit.isPending)
          submit.mutate();
      }}
    >
      <h2>{t(I18nKey.SCIENCE$PARAMETERS)}</h2>
      <p className="em-science-help">{t(I18nKey.SCIENCE$MINERU_HELP)}</p>
      <label>
        {t(I18nKey.SCIENCE$JOB_TITLE)}
        <input
          maxLength={80}
          value={options.title}
          onChange={(event) =>
            setOptions({ ...options, title: event.target.value })
          }
        />
      </label>
      <label className="em-science-upload">
        <Upload size={18} />
        <span>{t(I18nKey.SCIENCE$DOCUMENT_UPLOAD)}</span>
        <input
          type="file"
          accept=".pdf,.doc,.docx"
          aria-label={t(I18nKey.SCIENCE$DOCUMENT_UPLOAD)}
          onChange={(event) => {
            const selected = event.target.files?.[0];
            const valid =
              !!selected &&
              selected.size > 0 &&
              selected.size <= MAX_SCIENCE_DOCUMENT_BYTES &&
              /\.(pdf|doc|docx)$/i.test(selected.name);
            setFile(valid ? selected : null);
            setInvalid(!!selected && !valid);
            submit.reset();
          }}
        />
      </label>
      {file && <p className="break-all">{file.name}</p>}
      {invalid && (
        <p role="alert" className="em-science-error">
          {t(I18nKey.SCIENCE$DOCUMENT_ERROR)}
        </p>
      )}
      <div className="em-science-fields">
        <label>
          {t(I18nKey.SCIENCE$METHOD)}
          <select
            value={options.method}
            onChange={(event) =>
              setOptions({
                ...options,
                method: event.target.value as ScienceDocumentOptions["method"],
              })
            }
          >
            {app.methods.map((method) => (
              <option key={method} value={method}>
                {method}
              </option>
            ))}
          </select>
        </label>
        <label>
          {t(I18nKey.SCIENCE$DOCUMENT_LANGUAGE)}
          <select
            value={options.language}
            onChange={(event) =>
              setOptions({
                ...options,
                language: event.target
                  .value as ScienceDocumentOptions["language"],
              })
            }
          >
            <option value="ch">{t(I18nKey.SCIENCE$DOCUMENT_CHINESE)}</option>
            <option value="en">{t(I18nKey.SCIENCE$DOCUMENT_ENGLISH)}</option>
          </select>
        </label>
      </div>
      <label>
        <input
          type="checkbox"
          checked={options.enable_formula}
          onChange={(event) =>
            setOptions({ ...options, enable_formula: event.target.checked })
          }
        />
        {t(I18nKey.SCIENCE$DOCUMENT_FORMULA)}
      </label>
      <label>
        <input
          type="checkbox"
          checked={options.enable_table}
          onChange={(event) =>
            setOptions({ ...options, enable_table: event.target.checked })
          }
        />
        {t(I18nKey.SCIENCE$DOCUMENT_TABLE)}
      </label>
      {renderError(submit.error)}
      <BrandButton
        type="submit"
        variant="primary"
        testId="science-submit"
        isDisabled={!app.available || !file || invalid || submit.isPending}
        aria-busy={submit.isPending}
        startContent={<Play size={15} />}
      >
        {t(
          submit.isPending
            ? I18nKey.SCIENCE$SUBMITTING
            : I18nKey.SCIENCE$SUBMIT,
        )}
      </BrandButton>
      <p className="em-science-help">{t(I18nKey.SCIENCE$MINERU_STOP_NOTE)}</p>
    </form>
  );
}
