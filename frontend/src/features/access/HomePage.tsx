import { Navigate } from "react-router-dom";

import { visibleNavItems } from "../../layouts/navigation";
import { useCurrentUser } from "../auth/api";
import { NoAccessPage } from "./NoAccessPage";

/** "/" sends each user to the first page they may open, or explains that they have none yet. */
export function HomePage() {
  const { data: user } = useCurrentUser();
  const first = visibleNavItems(user)[0];
  return first ? <Navigate to={first.to} replace /> : <NoAccessPage />;
}
