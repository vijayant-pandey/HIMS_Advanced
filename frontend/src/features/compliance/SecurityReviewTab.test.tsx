import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { CurrentUser, SecurityReview } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { CompliancePage } from "./CompliancePage";

/** Security review tab (HIMS-SEC-011). Synthetic data. */

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const REVIEW: SecurityReview = {
  reviewed_on: "2026-11-11",
  reviewer: "Internal engineering review.",
  scope: "Everything built in Phase 1.",
  method: "Threat model checked against the code.",
  findings: [
    {
      code: "F-01",
      severity: "medium",
      area: "Sign-in sessions (13.1)",
      finding: "Screens that refresh themselves stayed signed in for ever.",
      fix: "Background refreshes no longer count as use.",
      status: "fixed",
    },
    {
      code: "F-06",
      severity: "info",
      area: "Dependencies",
      finding: "Moderate advisories in lint tools only.",
      fix: "Accepted: lint tools never reach a hospital.",
      status: "accepted",
    },
  ],
  checked: [{ area: "Injection", result: "No SQL built from user input." }],
  cases: [
    { number: 5, case: "A terminated employee reuses an old session.", status: "tested", status_label: "Tested", how: "Every session ends.", tests: 1 },
    { number: 3, case: "A nurse attempts to modify a signed doctor's note.", status: "waits", status_label: "Waits for the feature", how: "Phase 2.", tests: 0 },
  ],
  before_go_live: [{ ticket: "HIMS-SEC-021", what: "Independent security review and penetration test" }],
  encryption: { keys: 2, fields: [], on_older_keys: 3 },
};

function renderTab() {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = String(input);
    if (url.includes("/security/review/")) return json(REVIEW);
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
    email: "auditor@synthetic.test",
    display_name: "Synthetic Auditor",
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
  fireEvent.click(screen.getByRole("tab", { name: "Security review" }));
}

describe("Security review tab", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the findings, the spec 13.5 tests, the key status and what remains before go-live", async () => {
    renderTab();
    const findings = await screen.findByRole("table", { name: "Security review findings" });
    expect(within(findings).getByText("F-01")).toBeInTheDocument();
    expect(within(findings).getByText("Fixed")).toBeInTheDocument();
    expect(within(findings).getByText("Accepted")).toBeInTheDocument();

    const cases = screen.getByRole("table", { name: "Security tests" });
    expect(within(cases).getByText("Tested")).toBeInTheDocument();
    expect(within(cases).getByText("Waits for the feature")).toBeInTheDocument();
    expect(within(cases).getByText("1 automated test")).toBeInTheDocument();

    expect(screen.getByText(/3 stored secret\(s\) still need an older key/)).toBeInTheDocument();
    expect(screen.getByText("HIMS-SEC-021")).toBeInTheDocument();
  });
});
