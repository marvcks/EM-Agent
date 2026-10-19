import { useTranslation } from "react-i18next";
import { useNavigation } from "#/context/navigation-context";
import { I18nKey } from "#/i18n/declaration";

export function EmWorkspaceTopbar() {
  const { t } = useTranslation("openhands");
  const { currentPath } = useNavigation();
  const section = currentPath.startsWith("/settings")
    ? t(I18nKey.SIDEBAR$SETTINGS)
    : currentPath.startsWith("/customize")
      ? t(I18nKey.NAV$CUSTOMIZE)
      : t(I18nKey.BRANDING$EM_ASSISTANT);

  return (
    <header className="em-topbar">
      <div>
        {t(I18nKey.BRANDING$EM_WORKBENCH)}
        <span>/</span>
        {section}
      </div>
      <span className="em-space-label">{t(I18nKey.BRANDING$EM_SPACE)}</span>
    </header>
  );
}
