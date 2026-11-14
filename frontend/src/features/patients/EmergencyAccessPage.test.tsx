import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { CurrentUser, EmergencyAccess } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { EmergencyAccessPage } from "./EmergencyAccessPage";

// Invented people and numbers only.
const ACCESS: EmergencyAccess = {
  id: "a1",
  patient: "p1",
  patient_mrn: "MRN-00000007",
  patient_name: "Kavya Rao",
  user: "u2",
  user_name: "Head Of Cardiology",
  user_email: "hod@synthetic.test",
  reason: "Brought to the emergency room unconscious",
  created_at: "2026-11-14T05:00:00Z",
  expires_at: "2026-11-14T09:00:00Z",
  ended_at: "2026-11-14T06:00:00Z",
  ends_at: "2026-11-14T06:00:00Z",
  state: "to_review",
  reviewed_at: null,
  reviewed_by_name: null,
  outcome: "" as EmergencyAccess["outcome"], // not reviewed yet (blank)
  outcome_label: "",
  review_note: "",
  version: 2,
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

const page = (results: unknown[]) => json({ count: results.length, next: null, previous: null, results });

function renderPage(userId = "u1") {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST") return json({ ...ACCESS, state: "reviewed" });
    if (url.includes("/restricted-openings/")) {
      return page([
        {
          id: "e1",
          occurred_at: "2026-11-14T05:10:00Z",
          patient: "p1",
          patient_mrn: "MRN-00000007",
          actor_name: "Head Of Cardiology",
          facility_name: "Facility A",
          via: "emergency_access",
        },
      ]);
    }
    if (url.includes("state=to_review")) return page([ACCESS]);
    return page([]);
  });
  const user: CurrentUser = {
    id: userId,
    email: "records@synthetic.test",
    display_name: "Records Officer",
    staff_member_id: null,
    grants: [{ permission: "patients.records_correct", facility_id: null, department_id: null }],
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: true, required: true, verified: true, recovery_codes_remaining: 10, passkeys: 0 },
  };
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <EmergencyAccessPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

describe("Emergency access review (HIMS-PAT-006)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("reviews an ended emergency access; not appropriate needs a note", async () => {
    const fetchMock = renderPage();
    const table = await screen.findByRole("table", { name: "Emergency access" });
    const row = (await within(table).findByText("MRN-00000007")).closest("tr")!;
    expect(row).toHaveTextContent("Head Of Cardiology");
    expect(row).toHaveTextContent("Brought to the emergency room unconscious");
    expect(row).toHaveTextContent("Ended early");
    fireEvent.click(within(row).getByRole("button", { name: "Review" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.mouseDown(within(dialog).getByRole("combobox", { name: "Outcome" }));
    fireEvent.click(await screen.findByRole("option", { name: "Not appropriate (follow up)" }));
    expect(within(dialog).getByRole("button", { name: "Save review" })).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/^Note/), { target: { value: "No visit that day" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save review" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => init?.method === "POST");
      expect(String(call?.[0])).toContain("/patient-emergency-access/a1/review/");
      expect(JSON.parse(String(call?.[1]?.body))).toEqual({ outcome: "not_appropriate", note: "No visit that day", version: 2 });
    });
  });

  it("does not offer reviewing your own emergency access", async () => {
    renderPage("u2");
    const table = await screen.findByRole("table", { name: "Emergency access" });
    await within(table).findByText("MRN-00000007");
    expect(within(table).queryByRole("button", { name: "Review" })).not.toBeInTheDocument();
    expect(within(table).getByText(/someone else reviews it/)).toBeInTheDocument();
  });

  it("lists who opened restricted records and how", async () => {
    renderPage();
    fireEvent.click(await screen.findByRole("tab", { name: "Restricted record openings" }));
    const table = await screen.findByRole("table", { name: "Restricted record openings" });
    const row = (await within(table).findByText("MRN-00000007")).closest("tr")!;
    expect(row).toHaveTextContent("Head Of Cardiology");
    expect(row).toHaveTextContent("Emergency access");
  });
});
