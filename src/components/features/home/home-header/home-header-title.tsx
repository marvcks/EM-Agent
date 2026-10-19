import { useTranslation } from "react-i18next";
import { Typography } from "#/ui/typography";
import { I18nKey } from "#/i18n/declaration";
import { Atom } from "lucide-react";

export function HomeHeaderTitle() {
  const { t } = useTranslation("openhands");

  return (
    <div className="em-welcome flex w-full flex-col items-center gap-2 py-2">
      <span className="em-welcome-orbit" aria-hidden="true">
        <Atom size={35} strokeWidth={1.35} />
      </span>
      <span className="em-eyebrow">{t(I18nKey.BRANDING$EM_EYEBROW)}</span>
      <Typography.H1 className="w-full text-center leading-normal">
        {t(I18nKey.HOME$WHAT_TO_WORK_ON)}
      </Typography.H1>
      <p
        data-testid="home-header-subtitle"
        className="text-center text-[var(--oh-text-tertiary)]"
      >
        {t(I18nKey.HOME$ENGINEERING_TASKS_SUBHEADER)}
      </p>
    </div>
  );
}
