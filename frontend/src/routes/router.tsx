import { Navigate, createBrowserRouter } from "react-router-dom";

import { AccessPage } from "../features/accessControl/AccessPage";
import { AccountDetailPage } from "../features/accounts/AccountDetailPage";
import { AccountsPage } from "../features/accounts/AccountsPage";
import { AuditLogPage } from "../features/audit/AuditLogPage";
import { HomePage } from "../features/access/HomePage";
import { ActivatePage } from "../features/auth/ActivatePage";
import { ForgotPasswordPage } from "../features/auth/ForgotPasswordPage";
import { LoginPage } from "../features/auth/LoginPage";
import { RequireAuth } from "../features/auth/RequireAuth";
import { ResetPasswordPage } from "../features/auth/ResetPasswordPage";
import { DepartmentDetailPage } from "../features/facilities/DepartmentDetailPage";
import { DepartmentsPage } from "../features/facilities/DepartmentsPage";
import { FacilitiesPage } from "../features/facilities/FacilitiesPage";
import { LocationsPage } from "../features/locations/LocationsPage";
import { FeaturesPage } from "../features/featureFlags/FeaturesPage";
import { NumberingPage } from "../features/numbering/NumberingPage";
import { HospitalSettingsPage } from "../features/organization/HospitalSettingsPage";
import { SecurityPage } from "../features/security/SecurityPage";
import { CatalogsPage } from "../features/staff/CatalogsPage";
import { LicenceExpiryPage } from "../features/staff/LicenceExpiryPage";
import { StaffDetailPage } from "../features/staff/StaffDetailPage";
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
          { index: true, element: <HomePage /> },
          { path: "facilities", element: <FacilitiesPage /> },
          { path: "departments", element: <DepartmentsPage /> },
          { path: "departments/:id", element: <DepartmentDetailPage /> },
          { path: "locations", element: <LocationsPage /> },
          { path: "numbering", element: <NumberingPage /> },
          { path: "features", element: <FeaturesPage /> },
          { path: "staff", element: <StaffPage /> },
          { path: "staff/:id", element: <StaffDetailPage /> },
          { path: "licence-expiry", element: <LicenceExpiryPage /> },
          { path: "catalogs", element: <CatalogsPage /> },
          { path: "access", element: <AccessPage /> },
          { path: "accounts", element: <AccountsPage /> },
          { path: "accounts/:id", element: <AccountDetailPage /> },
          { path: "settings", element: <HospitalSettingsPage /> },
          { path: "audit", element: <AuditLogPage /> },
          { path: "security", element: <SecurityPage /> },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
]);
