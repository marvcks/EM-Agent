import { Navigate } from "react-router";
import { SCIENCE_APPS_PATH } from "#/api/science-apps-service";

export default function DisabledAppConnections() {
  return <Navigate to={SCIENCE_APPS_PATH} replace />;
}
