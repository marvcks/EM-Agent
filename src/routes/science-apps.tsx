import { useParams, useSearchParams, Navigate } from "react-router";
import { ScienceAppsPage } from "#/components/features/science-apps/science-apps-page";
import {
  SCIENCE_APPS_PATH,
  SCIENCE_JOB_PARAM,
  SCIENCE_APP_IDS,
  type ScienceAppId,
} from "#/api/science-apps-service";

export default function ScienceAppsRoute() {
  const { appId } = useParams();
  const [params, setParams] = useSearchParams();
  if (appId && !SCIENCE_APP_IDS.includes(appId as ScienceAppId)) {
    return <Navigate to={SCIENCE_APPS_PATH} replace />;
  }
  return (
    <ScienceAppsPage
      appId={appId}
      jobId={params.get(SCIENCE_JOB_PARAM)}
      onSelectJob={(id) => setParams(id ? { [SCIENCE_JOB_PARAM]: id } : {})}
    />
  );
}
