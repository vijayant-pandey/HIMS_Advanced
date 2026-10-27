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
      version: 1,
      floors: [
        {
          id: "fl1",
          level: 2,
          name: "Second floor",
          is_active: true,
          version: 1,
          wards: [
            {
              id: "w1",
              code: "w-gen",
              name: "General Ward",
              ward_type: "general",
              department: null,
              department_name: null,
              gender_restriction: "any",
              age_group: "any",
              is_active: true,
              version: 4,
              bed_counts: { available: 1, occupied: 1 },
              rooms: [
                {
                  id: "r1",
                  code: "r1",
                  name: "Room 1",
                  room_type: "general",
                  is_isolation_capable: false,
                  is_active: true,
                  version: 1,
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
    .mockImplementation(async (input, init) => {
      const url = String(input);
      if (url.endsWith("/locations/")) return json(tree);
      if (url.includes("/departments/"))
        return json({ count: 0, next: null, previous: null, results: [] });
      if (url.endsWith("/buildings/") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as { code: string };
        if (body.code === "main")
          return json(
            {
              title: "Validation failed",
              status: 400,
              code: "VALIDATION_ERROR",
              errors: [{ field: "code", message: "This code is already used in this facility." }],
            },
            400,
          );
        return json({ id: "b2" }, 201);
      }
      if (init?.method === "POST" || init?.method === "PATCH") {
        if (!url.includes("/status/")) return json({}, url.endsWith("/bulk/") ? 201 : 200);
      }
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

  it("shows no edit buttons to people who may only view", async () => {
    renderPage(["locations.view"]);
    await screen.findByText("General Ward");
    expect(screen.queryByRole("button", { name: "Add building" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Edit/ })).not.toBeInTheDocument();
  });

  it("adds a building and shows the server's message under the field", async () => {
    const fetchMock = renderPage(["locations.view", "locations.manage"]);
    fireEvent.click(await screen.findByRole("button", { name: "Add building" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Add building in Facility A")).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText(/^Code/), { target: { value: "main" } });
    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: "Main" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    expect(
      await within(dialog).findByText("This code is already used in this facility."),
    ).toBeInTheDocument();

    fireEvent.change(within(dialog).getByLabelText(/^Code/), { target: { value: "Block A" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));
    await vi.waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    const posts = fetchMock.mock.calls.filter(
      ([url, init]) => String(url).endsWith("/buildings/") && init?.method === "POST",
    );
    expect(JSON.parse(String(posts.at(-1)![1]!.body))).toEqual({
      facility: FACILITY_ID,
      code: "block-a", // typed "Block A": codes are made safe as you type
      name: "Main",
    });
    expect((posts.at(-1)![1]!.headers as Record<string, string>)["Idempotency-Key"]).toBeTruthy();
  });

  it("edits a ward with its current version and warns before deactivating", async () => {
    const fetchMock = renderPage(["locations.view", "locations.manage"]);
    fireEvent.click(await screen.findByRole("button", { name: "Edit General Ward" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).queryByLabelText(/^Code/)).not.toBeInTheDocument(); // codes never change
    fireEvent.change(within(dialog).getByLabelText(/^Name/), { target: { value: "Ward A" } });
    fireEvent.click(within(dialog).getByRole("switch", { name: "Active" }));
    expect(within(dialog).getByText(/Everything inside it must be deactivated first/)).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Save" }));

    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true),
    );
    const patch = fetchMock.mock.calls.find(([, init]) => init?.method === "PATCH")!;
    expect(String(patch[0])).toMatch(/\/wards\/w1\/$/);
    expect(JSON.parse(String(patch[1]!.body))).toMatchObject({
      version: 4,
      name: "Ward A",
      is_active: false,
      department: null,
    });
  });

  it("adds numbered beds and refuses codes already used in the ward", async () => {
    const fetchMock = renderPage(["locations.view", "locations.manage"]);
    fireEvent.click(await screen.findByRole("button", { name: "Add beds" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/Already used in this ward: B01, B02/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Add beds" })).toBeDisabled();

    fireEvent.change(within(dialog).getByLabelText("Start at"), { target: { value: "3" } });
    expect(within(dialog).getByText("Creates 4 bed(s): B03 … B06")).toBeInTheDocument();
    fireEvent.click(within(dialog).getByRole("button", { name: "Add beds" }));

    await vi.waitFor(() =>
      expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/beds/bulk/"))).toBe(true),
    );
    const call = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/beds/bulk/"))!;
    expect(JSON.parse(String(call[1]!.body))).toEqual({
      room: "r1",
      prefix: "b",
      start: 3,
      count: 4,
      bed_type: "general",
    });
  });

  it("opens bed details from the status dialog for people who manage locations", async () => {
    renderPage(["locations.view", "locations.manage", "beds.status.manage"]);
    fireEvent.click(await screen.findByLabelText("Bed B01, Available"));
    fireEvent.click(await screen.findByRole("button", { name: "Edit bed details" }));
    expect(await screen.findByText("Edit bed B01 · General Ward")).toBeInTheDocument();
    expect(screen.getByLabelText(/Bed type/)).toBeInTheDocument();
  });
});
