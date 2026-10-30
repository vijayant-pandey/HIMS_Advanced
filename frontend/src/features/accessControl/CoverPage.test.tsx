import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { CoverPage } from "./CoverPage";
import { MyCoverSection } from "./MyCoverSection";

const RAVI = { id: "u-ravi", display_name: "Ravi Covered", email: "ravi@synthetic.test" };
const ASHA = { id: "u-asha", display_name: "Asha Cover", email: "asha@synthetic.test" };
const COVER = {
  id: "d1",
  delegator: RAVI,
  delegate: ASHA,
  starts_at: "2026-11-04T00:00:00Z",
  ends_at: "2026-11-15T18:29:59Z",
  reason: "Annual leave",
  status: "active",
  status_label: "Active now",
  created_by_name: "Synthetic Admin",
  created_at: "2026-11-03T10:00:00Z",
  ended_at: null,
  ended_by_name: null,
  end_reason: "",
  lent_access: [
    {
      id: "c1",
      role_name: "HR / credentialing officer",
      scope: "Main Hospital",
      valid_from: "2026-11-04T00:00:00Z",
      valid_until: "2026-11-15T18:29:59Z",
      revoked_at: null,
      revocation_reason: "",
      is_active: true,
    },
  ],
  version: 2,
};
const account = (p: typeof RAVI) => ({
  ...p,
  is_active: true,
  activated: true,
  two_factor_enabled: false,
  invitation_expires_at: null,
  staff_member_id: null,
  roles: [],
  last_login: null,
  date_joined: "2026-01-01T00:00:00Z",
});

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderPage(grants: string[], ui = <CoverPage />, overrides: { list?: unknown; created?: unknown } = {}) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (init?.method === "POST" && url.endsWith("/end/")) return json({ ...COVER, status: "ended_early" });
    if (init?.method === "POST") return json(overrides.created ?? { ...COVER, skipped: [] }, 201);
    if (url.includes("/accounts/"))
      return json({ count: 2, next: null, previous: null, results: [account(RAVI), account(ASHA)] });
    if (url.includes("/delegable/"))
      return json([
        { id: "a-hr", role_name: "HR / credentialing officer", scope: "Main Hospital", valid_until: null, can_lend: true, why_not: "" },
        { id: "a-head", role_name: "Head of department", scope: "Main Hospital / Cardiology", valid_until: null, can_lend: true, why_not: "" },
        {
          id: "a-aud",
          role_name: "Auditor / compliance officer",
          scope: "Whole hospital",
          valid_until: null,
          can_lend: false,
          why_not: "Auditor access is never lent: auditors must stay independent.",
        },
      ]);
    if (url.includes("/my-delegations/")) return json([COVER]);
    if (url.includes("/access-delegations/")) return json(overrides.list ?? [COVER]);
    return json({});
  });
  const user: CurrentUser = {
    id: "u-asha",
    email: "admin@synthetic.test",
    display_name: "Synthetic Admin",
    staff_member_id: null,
    grants: grants.map((permission) => ({ permission, facility_id: null, department_id: null })),
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: true, required: true, verified: true, recovery_codes_remaining: 10 },
  };
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

const posted = (fetchMock: ReturnType<typeof renderPage>, ending: string) =>
  fetchMock.mock.calls.find(([url, init]) => init?.method === "POST" && String(url).endsWith(ending));

async function pick(dialog: HTMLElement, label: RegExp, name: string) {
  const input = within(dialog).getByLabelText(label);
  fireEvent.change(input, { target: { value: name.slice(0, 4) } });
  fireEvent.click(await screen.findByRole("option", { name: new RegExp(name) }));
}

describe("CoverPage (HIMS-IAM-017)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists who covers for whom, with the access lent", async () => {
    renderPage(["access.roles.view"]);
    const table = await screen.findByRole("table", { name: "Cover arrangements" });
    expect(await within(table).findByText("Asha Cover")).toBeInTheDocument();
    expect(table).toHaveTextContent("Ravi Covered");
    expect(table).toHaveTextContent("Annual leave");
    expect(table).toHaveTextContent("HR / credentialing officer · Main Hospital");
    expect(table).toHaveTextContent("Active now");
    // View-only: no buttons.
    expect(screen.queryByRole("button", { name: "Arrange cover" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^End cover/ })).not.toBeInTheDocument();
  });

  it("arranges cover with the chosen roles; auditor access cannot be ticked", async () => {
    const fetchMock = renderPage(["access.roles.view", "access.assignments.manage"], <CoverPage />, {
      created: {
        ...COVER,
        skipped: [{ role_name: "Head of department", scope: "Main Hospital / Cardiology", why: "Asha Cover already has this access." }],
      },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Arrange cover" }));
    const dialog = await screen.findByRole("dialog");
    await pick(dialog, /Person being covered/, "Ravi Covered");
    await pick(dialog, /Person covering/, "Asha Cover");
    const auditor = await within(dialog).findByRole("checkbox", { name: /Auditor \/ compliance officer/ });
    expect(auditor).toBeDisabled();
    expect(within(dialog).getByText(/auditors must stay independent/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("checkbox", { name: /Head of department/ })); // untick
    fireEvent.change(within(dialog).getByLabelText(/Ends on/), { target: { value: "2026-11-15" } });
    fireEvent.change(within(dialog).getByLabelText(/Reason/), { target: { value: "Annual leave" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Arrange cover" }));

    await vi.waitFor(() => expect(posted(fetchMock, "/access-delegations/")).toBeTruthy(), { timeout: 4000 });
    const body = JSON.parse(String(posted(fetchMock, "/access-delegations/")![1]!.body));
    expect(body).toMatchObject({
      delegator: "u-ravi",
      delegate: "u-asha",
      starts_at: null,
      reason: "Annual leave",
      assignments: ["a-hr"],
    });
    expect(new Date(body.ends_at).getTime()).toBeGreaterThan(new Date("2026-11-15T00:00:00").getTime());
    expect(await screen.findByText(/Asha Cover covers for Ravi Covered until/)).toBeInTheDocument();
    expect(screen.getByText(/Not lent: Head of department/)).toBeInTheDocument();
  });

  it("ends cover early with a reason and the version", async () => {
    const fetchMock = renderPage(["access.roles.view", "access.assignments.manage"]);
    fireEvent.click(await screen.findByRole("button", { name: "End cover by Asha Cover for Ravi Covered" }));
    const dialog = await screen.findByRole("dialog");
    const submit = within(dialog).getByRole("button", { name: "End cover now" });
    expect(submit).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Why is it ending early/), { target: { value: "Back early" } });
    fireEvent.click(submit);
    await vi.waitFor(() => expect(posted(fetchMock, "/d1/end/")).toBeTruthy(), { timeout: 4000 });
    expect(JSON.parse(String(posted(fetchMock, "/d1/end/")![1]!.body))).toEqual({ version: 2, reason: "Back early" });
  });

  it("shows an empty state", async () => {
    renderPage(["access.roles.view"], <CoverPage />, { list: [] });
    expect(await screen.findByText("No cover arranged at the moment.")).toBeInTheDocument();
  });

  it("tells people on their Security page that they are covering", async () => {
    renderPage([], <MyCoverSection />);
    expect(await screen.findByText("You cover for Ravi Covered")).toBeInTheDocument();
    expect(screen.getByText(/Annual leave/)).toBeInTheDocument();
  });
});
