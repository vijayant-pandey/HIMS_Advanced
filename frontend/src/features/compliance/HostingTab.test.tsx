import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { CurrentUser, HostingReadiness } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { CompliancePage } from "./CompliancePage";

/** Hosting readiness tab (HIMS-OPS-020). Synthetic data. */

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const check = (key: string, label: string, status: "ok" | "warn" | "fail", fix = "") => ({
  key,
  label,
  spec: "13.3",
  status,
  detail: `${label} detail.`,
  fix,
});

function renderTab(readiness: HostingReadiness) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/security/hosting/")) return json(readiness);
    if (url.includes("/compliance-summary/"))
      return json({
        country: "IN",
        requirements_total: 0,
        requirements_by_status: {},
        risks_open: 0,
        risks_high: 0,
        incidents_open: 0,
        notifications_overdue: 0,
      });
    return json([]);
  });
  const user: CurrentUser = {
    id: "u1",
    email: "officer@synthetic.test",
    display_name: "Synthetic Officer",
    staff_member_id: null,
    grants: [{ permission: "compliance.view", facility_id: null, department_id: null }],
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: true, required: true, verified: true, recovery_codes_remaining: 10, passkeys: 0 },
  };
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/compliance"]}>
        <CompliancePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByRole("tab", { name: "Hosting readiness" }));
}

describe("Hosting readiness tab", () => {
  afterEach(() => vi.restoreAllMocks());

  it("says a server fit for test data still needs some things before real data", async () => {
    renderTab({
      environment: "development",
      developer_pc: false,
      ready_to_host: true,
      ready_for_real_data: false,
      failing: 0,
      before_real_data: 1,
      checks: [
        check("https", "HTTPS only", "ok"),
        check("virus_scanner", "Uploads checked by a real virus scanner", "warn", "Run ClamAV next to HIMS."),
      ],
    });
    expect(await screen.findByText(/Fit to host with synthetic test data. 1 item/)).toBeInTheDocument();
    const table = screen.getByRole("table", { name: "Hosting readiness checks" });
    expect(within(table).getByText("Before real data")).toBeInTheDocument();
    expect(within(table).getByText("Run ClamAV next to HIMS.")).toBeInTheDocument();
  });

  it("explains that a developer PC is expected to fail", async () => {
    renderTab({
      environment: "local",
      developer_pc: true,
      ready_to_host: false,
      ready_for_real_data: false,
      failing: 1,
      before_real_data: 0,
      checks: [check("debug", "Debug pages off", "fail", "Set DJANGO_DEBUG=false.")],
    });
    expect(await screen.findByText(/expected on a developer PC/)).toBeInTheDocument();
    expect(screen.getByText("Must fix")).toBeInTheDocument();
  });
});
