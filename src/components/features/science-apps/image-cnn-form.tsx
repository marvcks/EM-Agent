import { useRef, useState, type ReactNode } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Play } from "lucide-react";
import { I18nKey } from "#/i18n/declaration";
import { BrandButton } from "#/components/features/settings/brand-button";
import { SCIENCE_QUERY_KEYS } from "#/hooks/query/query-keys";
import {
  scienceAppsService,
  type ScienceApplication,
  type ScienceJobRequest,
  type ScienceJob,
} from "#/api/science-apps-service";

const MAX_IMAGE_BYTES = 512 * 1024;
// @spec IC-004 — PNG or installed example submits directly to the science queue.
export function ImageCNNForm({
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
  const [encoded, setEncoded] = useState("");
  const [example, setExample] = useState(false);
  const [error, setError] = useState(false);
  const [reading, setReading] = useState(false);
  const [filename, setFilename] = useState("");
  const [cores, setCores] = useState(2);
  const [title, setTitle] = useState("");
  const selection = useRef(0);
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
        const input: ScienceJobRequest = {
          app_id: "image-cnn",
          task: "classification",
          method: "ResNet18",
          xyz: "",
          basis: "",
          charge: 0,
          multiplicity: 1,
          cores,
          memory_mb: 2048,
          title,
          image_example: example,
          image_base64: encoded,
        };
        submit.mutate(input);
      }}
    >
      <h2>{t(I18nKey.SCIENCE$PARAMETERS)}</h2>
      <label>
        {t(I18nKey.SCIENCE$JOB_TITLE)}
        <input
          maxLength={80}
          value={title}
          placeholder={app.name}
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>
      <label className="em-science-upload">
        {t(I18nKey.SCIENCE$IMAGE_UPLOAD)}
        <input
          type="file"
          accept=".png,image/png"
          aria-label={t(I18nKey.SCIENCE$IMAGE_UPLOAD)}
          onChange={(event) => {
            const token = ++selection.current;
            setEncoded("");
            setExample(false);
            setFilename("");
            setError(false);
            setReading(false);
            const file = event.target.files?.[0];
            if (!file) return;
            if (
              !file.size ||
              file.size > MAX_IMAGE_BYTES ||
              !/\.png$/i.test(file.name)
            ) {
              setError(true);
              return;
            }
            setReading(true);
            const reader = new FileReader();
            reader.onload = () => {
              if (token !== selection.current) return;
              setEncoded(String(reader.result).split(",")[1] ?? "");
              setFilename(file.name);
              setReading(false);
            };
            reader.onerror = () => {
              if (token !== selection.current) return;
              setError(true);
              setReading(false);
            };
            reader.readAsDataURL(file);
          }}
        />
      </label>
      <button
        type="button"
        onClick={() => {
          ++selection.current;
          setExample(true);
          setEncoded("");
          setError(false);
          setReading(false);
          setFilename("");
        }}
        aria-pressed={example}
      >
        {t(I18nKey.SCIENCE$IMAGE_EXAMPLE)}
      </button>
      {filename && <p>{filename}</p>}
      {error && (
        <p role="alert" className="em-science-error">
          {t(I18nKey.SCIENCE$IMAGE_ERROR)}
        </p>
      )}
      <p className="em-science-help">{t(I18nKey.SCIENCE$IMAGE_SCOPE)}</p>
      <label>
        {t(I18nKey.SCIENCE$CORES)}
        <input
          type="number"
          required
          min={1}
          max={app.max_cores}
          value={cores}
          onChange={(event) => setCores(Number(event.target.value))}
        />
      </label>
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
          reading ||
          error ||
          (!example && !encoded)
        }
        aria-busy={submit.isPending || reading}
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

export function ImageCNNResult({
  result,
}: {
  result: NonNullable<ScienceJob["result"]>;
}) {
  const { t } = useTranslation("openhands");
  if (result.probability_class1 === undefined) return null;
  return (
    <div>
      <div className="em-science-energy">
        <span>
          {t(
            result.predicted_class === 1
              ? I18nKey.SCIENCE$IMAGE_HIGH
              : I18nKey.SCIENCE$IMAGE_LOW,
          )}
        </span>
        <strong>
          {t(I18nKey.SCIENCE$IMAGE_PROBABILITY, {
            value: result.probability_class1.toFixed(4),
          })}
        </strong>
      </div>
      <p className="em-science-help">{t(I18nKey.SCIENCE$IMAGE_SCOPE)}</p>
      <p className="em-science-help">{t(I18nKey.SCIENCE$IMAGE_CAM)}</p>
    </div>
  );
}
