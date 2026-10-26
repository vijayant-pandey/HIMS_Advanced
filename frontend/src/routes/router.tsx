import { Navigate, createBrowserRouter } from "react-router-dom";

import { ActivatePage } from "../features/auth/ActivatePage";
import { LoginPage } from "../features/auth/LoginPage";
import { RequireAuth } from "../features/auth/RequireAuth";
import { FacilitiesPage } from "../features/facilities/FacilitiesPage";
import { StaffPage } from "../features/staff/StaffPage";
import { AppShell } from "../layouts/AppShell";

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  { path: "/activate", element: <ActivatePage /> },
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
