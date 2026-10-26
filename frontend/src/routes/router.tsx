import { Navigate, createBrowserRouter } from "react-router-dom";

import { ActivatePage } from "../features/auth/ActivatePage";
import { ForgotPasswordPage } from "../features/auth/ForgotPasswordPage";
import { LoginPage } from "../features/auth/LoginPage";
import { RequireAuth } from "../features/auth/RequireAuth";
import { ResetPasswordPage } from "../features/auth/ResetPasswordPage";
import { FacilitiesPage } from "../features/facilities/FacilitiesPage";
import { StaffPage } from "../features/staff/StaffPage";
import { AppShell } from "../layouts/AppShell";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/activate", element: <ActivatePage /> },
  { path: "/forgot-password", element: <ForgotPasswordPage /> },
  { path: "/reset-password", element: <ResetPasswordPage /> },
  {
    element: <RequireAuth />,
    children: [
      {
        element: <AppShell />,
        children: [
          { index: true, element: <Navigate to="/facilities" replace /> },
          { path: "facilities", element: <FacilitiesPage /> },
          { path: "staff", element: <StaffPage /> },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);
