import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { I18nKey } from "#/i18n/declaration";
import { createMolstarViewer } from "./molstar-viewer";

interface MolecularStructureViewerProps {
  path: string;
  text: string;
}

// @spec MOL-002 — Recreate on file changes and release resources on tab exit
export default function MolecularStructureViewer({
  path,
  text,
}: MolecularStructureViewerProps) {
  const { t } = useTranslation("openhands");
  const containerRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    let cancelled = false;
    let viewer: ReturnType<typeof createMolstarViewer> | undefined;
    let observer: ResizeObserver | undefined;
    setStatus("loading");
    try {
      viewer = createMolstarViewer(container, path, text);
      if (typeof ResizeObserver !== "undefined") {
        observer = new ResizeObserver(() => viewer?.resize());
        observer.observe(container);
      }
      void viewer.ready.then(
        () => {
          if (!cancelled) setStatus("ready");
        },
        () => {
          if (!cancelled) setStatus("error");
        },
      );
    } catch {
      setStatus("error");
    }
    return () => {
      cancelled = true;
      observer?.disconnect();
      viewer?.dispose();
    };
  }, [path, text, attempt]);

  return (
    <div
      className="flex h-full min-h-0 w-full flex-1 flex-col"
      data-testid="file-content-viewer-molecular"
    >
      <div className="relative min-h-0 flex-1 bg-surface">
        <div
          ref={containerRef}
          role="region"
          aria-label={t(I18nKey.FILES$MOLECULAR_CANVAS, { path })}
          className="absolute inset-0 overflow-hidden"
        />
        {status === "loading" && (
          <div
            role="status"
            className="absolute inset-0 flex items-center justify-center bg-surface text-sm text-muted"
          >
            {t(I18nKey.FILES$MOLECULAR_LOADING)}
          </div>
        )}
        {status === "error" && (
          <div
            role="alert"
            className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-surface p-6 text-sm text-foreground"
          >
            <p>{t(I18nKey.FILES$MOLECULAR_ERROR)}</p>
            <button
              type="button"
              onClick={() => setAttempt((value) => value + 1)}
              className="cursor-pointer rounded border border-border px-3 py-1 hover:bg-interactive-hover"
            >
              {t(I18nKey.FILES$MOLECULAR_RETRY)}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
