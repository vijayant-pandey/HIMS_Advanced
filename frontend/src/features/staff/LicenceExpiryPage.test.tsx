import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { ExpiringCredential } from "../../api/types";
import { LicenceExpiryPage, daysText } from "./LicenceExpiryPage";

function row(overrides: Partial<ExpiringCredential>): ExpiringCredential {
  return {
    id: "c1",
    credential_type: "medical_registration",
    registration_number: "KMC-100",
    issuing_authority: "Karnataka Medical Council",
    jurisdiction: "IN-KA",
    valid_from: null,
    expires_at: "2026-10-20",
    verification_status: "verified",
    verified_by: null,
    verified_by_name: null,
    verified_at: null,
    credential_type_label: "Medical council registration",
    expiry_state: "expired",
    staff_member_id: "s1",
    staff_name: "Dr Ravi Kumar",
    employee_number: "EMP-1",
    staff_type_label: "Doctor",
    days_left: -9,
    last_alert: "expired",
    last_alert_at: "2026-10-21T06:00:00Z",
    ...overrides,
  };
}

const ROWS = [
  row({}),
  row({
    id: "c2",
    registration_number: "KNC-200",
    expires_at: "2026-11-20",
    expiry_state: "expiring_soon",
    staff_member_id: "s2",
    staff_name: "Mary Joseph",
    days_left: 22,
    last_alert: null,
    last_alert_at: null,
  }),
];

function renderPage() {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(
    async () =>
      new Response(JSON.stringify(ROWS), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <LicenceExpiryPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

describe("LicenceExpiryPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists expired and soon-to-expire licences with links to the person", async () => {
    renderPage();
    expect(await screen.findByText("Dr Ravi Kumar")).toBeInTheDocument();
    expect(screen.getByText("Expired 9 days ago")).toBeInTheDocument();
    expect(screen.getByText("In 22 days")).toBeInTheDocument();
    expect(screen.getByText("1 expired")).toBeInTheDocument();
    expect(screen.getByText("Expired notice")).toBeInTheDocument();
    expect(screen.getByText("Not yet")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Mary Joseph" }).getAttribute("href")).toBe("/staff/s2");
  });

  it("asks the server for the chosen window and can hide expired ones", async () => {
    const fetchMock = renderPage();
    await screen.findByText("Dr Ravi Kumar");
    fireEvent.click(screen.getByRole("switch", { name: "Include expired" }));
    await vi.waitFor(
      () =>
        expect(fetchMock.mock.calls.some(([u]) => String(u).includes("include_expired=false"))).toBe(true),
      { timeout: 4000 },
    );
  });

  it("describes days in plain words", () => {
    expect(daysText(-1)).toBe("Expired 1 day ago");
    expect(daysText(0)).toBe("Expires today");
    expect(daysText(1)).toBe("In 1 day");
  });
});
