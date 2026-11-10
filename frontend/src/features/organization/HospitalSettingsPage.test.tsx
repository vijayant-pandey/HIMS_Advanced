import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import type { CurrentUser, Organization } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { HospitalSettingsPage } from "./HospitalSettingsPage";

const ORGANIZATION: Organization = {
  id: "o1",
  legal_name: "Synthetic Health Pvt Ltd",
  display_name: "Synthetic Health",
  country: "IN",
  default_timezone: "Asia/Kolkata",
  default_currency: "INR",
  status: "active",
  leave_year_start_month: 1,
  has_logo: false,
  letterhead_address: "1 Synthetic Road",
  letterhead_phone: "",
  letterhead_email: "",
  letterhead_website: "",
  letterhead_registration: "",
  letterhead_footer: "",
  version: 4,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-11-09T08:00:00Z",
};

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function renderPage(grants: string[], organization: Organization = ORGANIZATION, refuseLogo = false) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    if (url.endsWith("/organization/letterhead/")) {
      return json({
        display_name: organization.display_name,
        legal_name: organization.legal_name,
        lines: [organization.letterhead_address],
        has_logo: organization.has_logo,
        version: organization.version,
      });
    }
    if (url.endsWith("/organization/logo/") && refuseLogo) {
      return json(
        {
          title: "Invalid",
          status: 400,
          code: "VALIDATION_ERROR",
          errors: [{ field: "file", message: "The logo must be a PNG or JPG picture.", code: "invalid" }],
        },
        400,
      );
    }
    if (init?.method === "POST" || init?.method === "PATCH") return json(organization);
    return json(organization);
  });
  const user: CurrentUser = {
    id: "u1",
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
      <HospitalSettingsPage />
    </QueryClientProvider>,
  );
  return fetchMock;
}

const MANAGE = ["organization.view", "organization.manage"];
const logoFile = () => new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], "logo.png", { type: "image/png" });

describe("Letterhead on Hospital settings (HIMS-ORG-006)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the letterhead as it appears on paper", async () => {
    renderPage(["organization.view"]);
    const section = await screen.findByRole("region", { name: "Letterhead" });
    expect(await within(section).findByText("1 Synthetic Road")).toBeInTheDocument();
    expect(within(section).getByText("Synthetic Health")).toBeInTheDocument();
    expect(within(section).queryByRole("button", { name: "Edit letterhead" })).toBeNull();
    expect(within(section).queryByRole("button", { name: "Upload logo" })).toBeNull();
    expect(within(section).getByRole("button", { name: "Print a sample" })).toBeInTheDocument();
  });

  it("uploads a logo as a file", async () => {
    const fetchMock = renderPage(MANAGE);
    const input = await screen.findByLabelText("Logo file");
    fireEvent.change(input, { target: { files: [logoFile()] } });
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([url, init]) => init?.method === "POST" && String(url).endsWith("/organization/logo/"));
      expect((call?.[1]?.body as FormData).get("file")).toBeInstanceOf(File);
    });
  });

  it("refuses a logo over the limit without sending it", async () => {
    const fetchMock = renderPage(MANAGE);
    const big = new File([new Uint8Array(2 * 1024 * 1024 + 1)], "big.png", { type: "image/png" });
    fireEvent.change(await screen.findByLabelText("Logo file"), { target: { files: [big] } });
    expect(await screen.findByText(/too large/)).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([url, init]) => init?.method === "POST" && String(url).includes("/logo/"))).toBe(false);
  });

  it("shows why the server refused a file", async () => {
    renderPage(MANAGE, ORGANIZATION, true);
    fireEvent.change(await screen.findByLabelText("Logo file"), { target: { files: [logoFile()] } });
    expect(await screen.findByText(/must be a PNG or JPG/)).toBeInTheDocument();
  });

  it("removes a logo only when there is one", async () => {
    const fetchMock = renderPage(MANAGE, { ...ORGANIZATION, has_logo: true });
    const section = await screen.findByRole("region", { name: "Letterhead" });
    expect(within(section).getByRole("button", { name: "Replace logo" })).toBeInTheDocument();
    fireEvent.click(within(section).getByRole("button", { name: "Remove logo" }));
    await waitFor(() =>
      expect(fetchMock.mock.calls.some(([url, init]) => init?.method === "POST" && String(url).endsWith("/logo/remove/"))).toBe(true),
    );
  });

  it("saves the details with the hospital's version", async () => {
    const fetchMock = renderPage(MANAGE);
    fireEvent.click(await screen.findByRole("button", { name: "Edit letterhead" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.change(within(dialog).getByLabelText("Phone"), { target: { value: "+91 20 0000" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await waitFor(() => {
      const call = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH");
      expect(JSON.parse(String(call?.[1]?.body))).toMatchObject({
        version: 4,
        letterhead_phone: "+91 20 0000",
        letterhead_address: "1 Synthetic Road",
      });
    });
  });
});
