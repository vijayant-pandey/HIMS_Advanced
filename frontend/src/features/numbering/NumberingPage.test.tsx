import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { CurrentUser, NumberingScheme } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { NumberingPage } from "./NumberingPage";

const mrn: NumberingScheme = {
  id: "s1",
  document_type: "mrn",
  document_type_label: "Patient record number (MRN)",
  facility: null,
  facility_name: null,
  prefix: "MRN",
  separator: "-",
  include_facility_code: false,
  period: "none",
  year_format: "full",
  financial_year_start_month: 4,
  padding: 8,
  start_at: 1,
  is_active: true,
  next_number: "MRN-00000001",
  version: 3,
  created_at: "2026-10-27T00:00:00Z",
  updated_at: "2026-10-27T00:00:00Z",
};

const invoice: NumberingScheme = {
  ...mrn,
  id: "s2",
  document_type: "invoice",
  document_type_label: "Invoice number",
  prefix: "INV",
  separator: "/",
  period: "financial_year",
  year_format: "short",
  padding: 6,
  next_number: "INV/26-27/000001",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage(grants: CurrentUser["grants"]) {
  const user: CurrentUser = {
    id: "u1",
    email: "admin@synthetic.test",
    display_name: "Synthetic Admin",
    staff_member_id: null,
    grants,
    organization: { display_name: "Synthetic Health", country: "IN" },
    mfa: { enabled: true, required: true, verified: true, recovery_codes_remaining: 10 },
  };
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/numbering-schemes/preview/")) {
      const body = JSON.parse(String(init!.body)) as { prefix: string };
      return json({ example: `${body.prefix}-00000001`, longest: `${body.prefix}-99999999`, errors: {} });
    }
    if (url.includes("/numbering-schemes/s1/next-number/")) return json({ ...mrn, version: 4 });
    if (url.includes("/numbering-schemes/s1/")) return json({ ...mrn, version: 4 });
    if (url.includes("/numbering-schemes/")) return json([mrn, invoice]);
    if (url.includes("/issued-numbers/"))
      return json({ count: 0, next: null, previous: null, results: [] });
    return json({ count: 0, next: null, previous: null, results: [] }); // facilities
  });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryData(currentUserKey, user);
  render(
    <QueryClientProvider client={queryClient}>
      <NumberingPage />
    </QueryClientProvider>,
  );
  return fetchMock;
}

const ORG_ADMIN = [
  { permission: "numbering.view", facility_id: null, department_id: null },
  { permission: "numbering.manage", facility_id: null, department_id: null },
];

describe("NumberingPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows each number type with its next number", async () => {
    renderPage(ORG_ADMIN);
    expect(await screen.findByText("MRN-00000001")).toBeInTheDocument();
    expect(screen.getByText("INV/26-27/000001")).toBeInTheDocument();
    expect(screen.getByText("Every financial year (from April)")).toBeInTheDocument();
    expect(screen.getAllByText("Whole hospital")).toHaveLength(2);
    expect(await screen.findByText(/None yet/)).toBeInTheDocument();
  });

  it("hides edit buttons from people who may only view", async () => {
    renderPage([{ permission: "numbering.view", facility_id: null, department_id: null }]);
    await screen.findByText("MRN-00000001");
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
  });

  it("previews while typing and saves with the current version", async () => {
    const fetchMock = renderPage(ORG_ADMIN);
    const row = (await screen.findByText("MRN-00000001")).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/Prefix/), { target: { value: "uhid" } });

    expect(await within(dialog).findByText("UHID-00000001", {}, { timeout: 2000 })).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true),
    );
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")!;
    expect(String(patch[0])).toMatch(/\/numbering-schemes\/s1\/$/);
    const body = JSON.parse(String(patch[1]!.body)) as Record<string, unknown>;
    expect(body).toMatchObject({ version: 3, prefix: "UHID", padding: 8, is_active: true });
    expect(body).not.toHaveProperty("document_type");
  });

  it("continues numbering from a previous system", async () => {
    const fetchMock = renderPage(ORG_ADMIN);
    const row = (await screen.findByText("MRN-00000001")).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "Continue from…" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText(/Next running number/), {
      target: { value: "54322" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await vi.waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) => String(url).endsWith("/s1/next-number/")),
      ).toBe(true),
    );
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/next-number/"))!;
    expect(JSON.parse(String(call[1]!.body))).toEqual({ version: 3, next_value: 54322 });
    expect((call[1]!.headers as Record<string, string>)["Idempotency-Key"]).toBeTruthy();
  });
});
