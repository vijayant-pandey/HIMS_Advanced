import { Box, CircularProgress } from "@mui/material";
import { Navigate, Outlet, useLocation } from "react-router-dom";

import { ErrorAlert } from "../../components/ErrorAlert";
import { useCurrentUser } from "./api";

export function RequireAuth() {
  const location = useLocation();
  const { data: user, isPending, error } = useCurrentUser();

  if (isPending) {
    return (
      <Box sx={{ display: "grid", placeItems: "center", minHeight: "100vh" }}>
        <CircularProgress aria-label="Loading" />
      </Box>
    );
  }
  if (error) return <ErrorAlert error={error} />;
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
  // Privileged roles must pass two-factor first (HIMS-IAM-005); the API enforces this too.
  if (user.mfa.required && !user.mfa.verified && location.pathname !== "/security") {
    return <Navigate to="/security" replace />;
  }
  return <Outlet />;
}
