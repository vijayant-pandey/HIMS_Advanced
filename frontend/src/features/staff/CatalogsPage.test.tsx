import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { CurrentUser } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { CatalogsPage } from "./CatalogsPage";

const TITLES = [
  {
    id: "t1",
    code: "in-consultant",
    name: "Consultant",
    category: "medical",
    country: "IN",
    seniority: 6,
    description: "",
    is_active: true,
    is_custom: false,
    version: 1,
  },
  {
    id: "t2",
    code: "in-senior-dialysis-technician",
    name: "Senior Dialysis Technician",
    category: "allied_health",
    country: "IN",
    seniority: 4,
    description: "",
    is_active: false,
    is_custom: true,
    version: 3,
  },
];

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage(grants: string[]) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    if (init?.method && init.method !== "GET") return json(TITLES[0], init.method === "POST" ? 201 : 200);
    return String(input).includes("/designations/") ? json(TITLES) : json([]);
  });
  const user: CurrentUser = {
    id: "u1",
    email: "hr@synthetic.test",
    display_name: "Synthetic HR",
    staff_member_id: null,
    grants: grants.map((permission) => ({ permission, facility_id: null, department_id: null })),
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: true, required: true, verified: true, recovery_codes_remaining: 10 },
  };
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  render(
    <QueryClientProvider client={queryClient}>
      <CatalogsPage />
    </QueryClientProvider>,
  );
  return fetchMock;
}

describe("CatalogsPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists standard and hospital entries, including switched-off ones", async () => {
    const fetchMock = renderPage(["staff.view"]);
    expect(await screen.findByText("Consultant")).toBeInTheDocument();
    expect(screen.getByText("Added by hospital")).toBeInTheDocument();
    expect(screen.getByText("Standard")).toBeInTheDocument();
    expect(String(fetchMock.mock.calls[0]![0])).toContain("include_inactive=true");
    expect(screen.queryByRole("button", { name: "Add job title" })).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Consultant in use" })).toBeDisabled();
  });

  it("adds a job title", async () => {
    const fetchMock = renderPage(["staff.view", "catalogs.manage"]);
    fireEvent.click(await screen.findByRole("button", { name: "Add job title" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: "Cath Lab Technician" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await vi.waitFor(
      () => expect(fetchMock.mock.calls.some(([, i]) => i?.method === "POST")).toBe(true),
      { timeout: 4000 },
    );
    const call = fetchMock.mock.calls.find(([, i]) => i?.method === "POST")!;
    expect(String(call[0])).toMatch(/\/designations\/$/);
    expect(JSON.parse(String(call[1]!.body))).toEqual({
      name: "Cath Lab Technician",
      category: "medical",
      country: "",
      seniority: 3,
      description: "",
    });
  });

  it("switches an entry back on with its current version", async () => {
    const fetchMock = renderPage(["staff.view", "catalogs.manage"]);
    fireEvent.click(await screen.findByRole("switch", { name: "Senior Dialysis Technician in use" }));
    await vi.waitFor(
      () => expect(fetchMock.mock.calls.some(([, i]) => i?.method === "PATCH")).toBe(true),
      { timeout: 4000 },
    );
    const call = fetchMock.mock.calls.find(([, i]) => i?.method === "PATCH")!;
    expect(String(call[0])).toMatch(/\/designations\/t2\/$/);
    expect(JSON.parse(String(call[1]!.body))).toEqual({ version: 3, is_active: true });
  });

  it("searches by name", async () => {
    renderPage(["staff.view"]);
    await screen.findByText("Consultant");
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "dialysis" } });
    expect(screen.queryByText("Consultant")).not.toBeInTheDocument();
    expect(screen.getByText("Senior Dialysis Technician")).toBeInTheDocument();
  });
});
