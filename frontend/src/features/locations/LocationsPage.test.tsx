import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { CurrentUser, FacilityLocations } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { LocationsPage } from "./LocationsPage";

const FACILITY_ID = "f1";

const tree: FacilityLocations = {
  facility: FACILITY_ID,
  bed_counts: { available: 1, occupied: 1 },
  buildings: [
    {
      id: "b1",
      code: "main",
      name: "Main Block",
      is_active: true,
      floors: [
        {
          id: "fl1",
          level: 2,
          name: "Second floor",
          is_active: true,
          wards: [
            {
              id: "w1",
              code: "w-gen",
              name: "General Ward",
              ward_type: "general",
              department: null,
              gender_restriction: "any",
              age_group: "any",
              is_active: true,
              bed_counts: { available: 1, occupied: 1 },
              rooms: [
                {
                  id: "r1",
                  code: "r1",
                  name: "Room 1",
                  room_type: "general",
                  is_isolation_capable: false,
                  is_active: true,
                  beds: [
                    bed("bed1", "b01", "available"),
                    bed("bed2", "b02", "occupied"),
                  ],
                },
              ],
            },
          ],
        },
      ],
    },
  ],
};

function bed(id: string, code: string, status: string) {
  return {
    id,
    code,
    bed_type: "general",
    status,
    status_reason: "",
    is_active: true,
    version: 1,
  };
}

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage(permissions: string[]) {
  const user: CurrentUser = {
    id: "u1",
    email: "clerk@synthetic.test",
    display_name: "Ward Clerk",
    staff_member_id: null,
    grants: permissions.map((permission) => ({
      permission,
      facility_id: FACILITY_ID,
      department_id: null,
    })),
    mfa: {
      enabled: false,
      required: false,
      verified: false,
      recovery_codes_remaining: 0,
    },
  };
  const fetchMock = vi
    .spyOn(globalThis, "fetch")
    .mockImplementation(async (input) => {
      const url = String(input);
      if (url.endsWith("/locations/")) return json(tree);
      if (url.includes("/facilities/"))
        return json({
          count: 1,
          next: null,
          previous: null,
          results: [{ id: FACILITY_ID, name: "Facility A" }],
        });
      return json({ ...bed("bed1", "b01", "maintenance"), version: 2 });
    });
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  queryClient.setQueryData(currentUserKey, user);
  render(
    <QueryClientProvider client={queryClient}>
      <LocationsPage />
    </QueryClientProvider>,
  );
  return fetchMock;
}

describe("LocationsPage", () => {
  afterEach(() => vi.restoreAllMocks());

  it("shows the structure with bed counts", async () => {
    renderPage(["locations.view"]);
    expect(await screen.findByText("General Ward")).toBeInTheDocument();
    expect(screen.getAllByText("Available: 1").length).toBeGreaterThan(0);
    expect(screen.getByLabelText("Bed B02, Occupied")).toBeInTheDocument();
  });

  it("lets a bed manager put a bed under maintenance with a reason", async () => {
    const fetchMock = renderPage(["locations.view", "beds.status.manage"]);
    fireEvent.click(await screen.findByLabelText("Bed B01, Available"));
    const dialog = await screen.findByRole("dialog");
    fireEvent.mouseDown(within(dialog).getByRole("combobox"));
    fireEvent.click(await screen.findByRole("option", { name: "Maintenance" }));
    const save = within(dialog).getByRole("button", { name: "Save" });
    expect(save).toBeDisabled(); // a reason is required
    fireEvent.change(within(dialog).getByLabelText(/Reason/), {
      target: { value: "Broken side rail" },
    });
    fireEvent.click(save);

    await vi.waitFor(() =>
      expect(
        fetchMock.mock.calls.some(([url]) =>
          String(url).endsWith("/beds/bed1/status/"),
        ),
      ).toBe(true),
    );
    const call = fetchMock.mock.calls.find(([url]) =>
      String(url).endsWith("/status/"),
    )!;
    expect(JSON.parse(String(call[1]!.body))).toEqual({
      version: 1,
      status: "maintenance",
      reason: "Broken side rail",
    });
    expect(
      (call[1]!.headers as Record<string, string>)["Idempotency-Key"],
    ).toBeTruthy();
  });

  it("explains that occupied beds are managed by admissions", async () => {
    renderPage(["locations.view", "beds.status.manage"]);
    fireEvent.click(await screen.findByLabelText("Bed B02, Occupied"));
    expect(
      await screen.findByText(/changes through admission/),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Save" }),
    ).not.toBeInTheDocument();
  });
});
