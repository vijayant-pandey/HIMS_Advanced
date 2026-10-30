import type { ComponentType } from "react";
import { Navigate, createBrowserRouter } from "react-router-dom";

import { HomePage } from "../features/access/HomePage";
import { LoginPage } from "../features/auth/LoginPage";
import { RequireAuth } from "../features/auth/RequireAuth";
import { AppShell } from "../layouts/AppShell";
import { RouteErrorPage } from "./RouteErrorPage";

/*
 * Route-level code splitting (HIMS-PLAT-015). Sign-in, the menu frame and the home page load
 * at once; every other screen is downloaded the first time it is opened, so the first page
 * appears faster. While a screen loads, AppShell shows a thin progress bar. If a screen cannot
 * be loaded (e.g. HIMS was updated while the tab was open), RouteErrorPage offers a reload.
 */
const screen =
  <M,>(load: () => Promise<M>, pick: (module: M) => ComponentType) =>
  async () => ({ Component: pick(await load()) });

const auth = () => import("../features/auth/authPages");
const access = () => import("../features/accessControl/AccessPage");
const reviews = () => import("../features/accessControl/AccessReviewsPage");
const audit = () => import("../features/audit/AuditIntegrityPage");
const staff = () => import("../features/staff/StaffDetailPage");

export const routes = [
  { path: "/login", element: <LoginPage /> },
  { path: "/activate", lazy: screen(auth, (m) => m.ActivatePage) },
  { path: "/forgot-password", lazy: screen(auth, (m) => m.ForgotPasswordPage) },
  { path: "/reset-password", lazy: screen(auth, (m) => m.ResetPasswordPage) },
  {
    element: <RequireAuth />,
    errorElement: <RouteErrorPage />,
    children: [
      {
        element: <AppShell />,
        children: [
          {
            errorElement: <RouteErrorPage />,
            children: [
              { index: true, element: <HomePage /> },
              {
                path: "facilities",
                lazy: screen(() => import("../features/facilities/FacilitiesPage"), (m) => m.FacilitiesPage),
              },
              {
                path: "departments",
                lazy: screen(() => import("../features/facilities/DepartmentsPage"), (m) => m.DepartmentsPage),
              },
              {
                path: "departments/:id",
                lazy: screen(
                  () => import("../features/facilities/DepartmentDetailPage"),
                  (m) => m.DepartmentDetailPage,
                ),
              },
              {
                path: "locations",
                lazy: screen(() => import("../features/locations/LocationsPage"), (m) => m.LocationsPage),
              },
              {
                path: "numbering",
                lazy: screen(() => import("../features/numbering/NumberingPage"), (m) => m.NumberingPage),
              },
              {
                path: "features",
                lazy: screen(() => import("../features/featureFlags/FeaturesPage"), (m) => m.FeaturesPage),
              },
              { path: "staff", lazy: screen(() => import("../features/staff/StaffPage"), (m) => m.StaffPage) },
              { path: "staff/:id", lazy: screen(staff, (m) => m.StaffDetailPage) },
              {
                path: "licence-expiry",
                lazy: screen(() => import("../features/staff/LicenceExpiryPage"), (m) => m.LicenceExpiryPage),
              },
              {
                path: "catalogs",
                lazy: screen(() => import("../features/staff/CatalogsPage"), (m) => m.CatalogsPage),
              },
              { path: "access", lazy: screen(access, (m) => m.AccessPage) },
              { path: "access-reviews", lazy: screen(reviews, (m) => m.AccessReviewsPage) },
              { path: "access-reviews/:id", lazy: screen(reviews, (m) => m.AccessReviewDetailPage) },
              {
                path: "cover",
                lazy: screen(() => import("../features/accessControl/CoverPage"), (m) => m.CoverPage),
              },
              {
                path: "accounts",
                lazy: screen(() => import("../features/accounts/AccountsPage"), (m) => m.AccountsPage),
              },
              {
                path: "accounts/:id",
                lazy: screen(() => import("../features/accounts/AccountDetailPage"), (m) => m.AccountDetailPage),
              },
              {
                path: "settings",
                lazy: screen(
                  () => import("../features/organization/HospitalSettingsPage"),
                  (m) => m.HospitalSettingsPage,
                ),
              },
              {
                path: "audit",
                lazy: screen(() => import("../features/audit/AuditLogPage"), (m) => m.AuditLogPage),
              },
              { path: "audit/integrity", lazy: screen(audit, (m) => m.AuditIntegrityPage) },
              { path: "audit/integrity/:id", lazy: screen(audit, (m) => m.AuditIntegrityDetailPage) },
              {
                path: "notifications",
                lazy: screen(() => import("../features/notifications/NotificationsPage"), (m) => m.NotificationsPage),
              },
              {
                path: "security",
                lazy: screen(() => import("../features/security/SecurityPage"), (m) => m.SecurityPage),
              },
            ],
          },
        ],
      },
    ],
  },
  { path: "*", element: <Navigate to="/" replace /> },
];

export const router = createBrowserRouter(routes);
