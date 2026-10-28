import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { CurrentUser, FeatureState } from "../../api/types";
import { ThemeSelectionProvider } from "../../app/ThemeSelection";
import { currentUserKey } from "../auth/api";
import { ForgotPasswordPage } from "../auth/ForgotPasswordPage";
import { LoginPage } from "../auth/LoginPage";
import { FeaturesPage } from "./FeaturesPage";

const unset = { setting: "default" as const, version: 1, reason: "", updated_by_name: null, updated_at: null };

function feature(overrides: Partial<FeatureState>): FeatureState {
  return {
    key: "locations.module",
    name: "Locations and beds",
    description: "Buildings, wards, rooms and beds.",
    category: "Hospital setup",
    scope: "facility",
    available: true,
    planned_phase: "",
    countries: null,
    offered_in_country: true,
    default: true,
    hospital: unset,
    facility: null,
    enabled: true,
    ...overrides,
  };
}

const FEATURES: FeatureState[] = [
  feature({}),
  feature({
    key: "auth.two_factor_for_everyone",
    name: "Two-factor sign-in for all staff",
    category: "Sign-in and security",
    scope: "organization",
    default: false,
    enabled: false,
    hospital: {
      setting: "off",
      version: 2,
      reason: "Board decision",
      updated_by_name: "Synthetic Admin",
      updated_at: "2026-10-28T00:00:00Z",
    },
  }),
  feature({
    key: "patients.registration",
    name: "Patient registration",
    category: "Clinical modules",
    available: false,
    planned_phase: "Phase 2",
    enabled: false,
    default: false,
  }),
];

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function mockApi(effective = { hospital: { "auth.self_service_password_reset": true }, facilities: {} }) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.includes("/features/effective/")) return json(effective);
    if (url.includes("/change/")) return json({ ...FEATURES[1], enabled: true });
    if (url.includes("/features/")) return json(FEATURES);
    if (url.endsWith("/auth/csrf/")) return new Response(null, { status: 204 });
    void init;
    return json({ count: 0, next: null, previous: null, results: [] });
  });
}

function renderWith(element: React.ReactNode, user: CurrentUser | null) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  render(
    <ThemeSelectionProvider>
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{element}</MemoryRouter>
      </QueryClientProvider>
    </ThemeSelectionProvider>,
  );
}

function admin(grants: string[]): CurrentUser {
  return {
    id: "u1",
    email: "admin@synthetic.test",
    display_name: "Synthetic Admin",
    staff_member_id: null,
    grants: grants.map((permission) => ({ permission, facility_id: null, department_id: null })),
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: true, required: true, verified: true, recovery_codes_remaining: 10 },
  };
}

describe("FeaturesPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists features by group with their setting, last change and planned phase", async () => {
    mockApi();
    renderWith(<FeaturesPage />, admin(["features.view", "features.manage"]));
    expect(await screen.findByText("Locations and beds")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Clinical modules" })).toBeInTheDocument();
    expect(screen.getByText("Coming in Phase 2")).toBeInTheDocument();
    expect(screen.getByText("Board decision · Synthetic Admin")).toBeInTheDocument();
    // planned features cannot be changed
    expect(screen.queryByRole("button", { name: "Change Patient registration" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Change Locations and beds" })).toBeInTheDocument();
  });

  it("hides change buttons from people who may only view", async () => {
    mockApi();
    renderWith(<FeaturesPage />, admin(["features.view"]));
    await screen.findByText("Locations and beds");
    expect(screen.queryByRole("button", { name: /^Change/ })).not.toBeInTheDocument();
  });

  it("asks for a reason, warns about two-factor and sends the current version", async () => {
    const fetchMock = mockApi();
    renderWith(<FeaturesPage />, admin(["features.view", "features.manage"]));
    fireEvent.click(await screen.findByRole("button", { name: "Change Two-factor sign-in for all staff" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("radio", { name: "On" }));
    expect(within(dialog).getByText(/including you if you have none/)).toBeInTheDocument();
    const save = within(dialog).getByRole("button", { name: "Save" });
    expect(save).toBeDisabled(); // a reason is required
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Policy 12" } });
    fireEvent.click(save);

    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/change/"))).toBe(true),
    );
    const call = fetchMock.mock.calls.find(([url]) => String(url).includes("/change/"))!;
    expect(String(call[0])).toMatch(/\/features\/auth\.two_factor_for_everyone\/change\/$/);
    expect(JSON.parse(String(call[1]!.body))).toEqual({
      facility: null,
      setting: "on",
      reason: "Policy 12",
      version: 2,
    });
  });
});

describe("Forgot-password feature on the sign-in pages", () => {
  afterEach(() => vi.restoreAllMocks());
  const off = { hospital: { "auth.self_service_password_reset": false }, facilities: {} };

  it("shows the link when the hospital allows it", async () => {
    mockApi();
    renderWith(<LoginPage />, null);
    expect(await screen.findByText("Forgot password?")).toBeInTheDocument();
  });

  it("hides the link and explains on the reset page when it is off", async () => {
    mockApi(off);
    renderWith(<LoginPage />, null);
    await vi.waitFor(() => expect(screen.queryByText("Forgot password?")).not.toBeInTheDocument());
  });

  it("tells staff to ask their administrator when it is off", async () => {
    mockApi(off);
    renderWith(<ForgotPasswordPage />, null);
    expect(await screen.findByText(/Ask your administrator/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send reset link" })).not.toBeInTheDocument();
  });
});
