import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import type { CurrentUser } from "../../api/types";
import { currentUserKey } from "../auth/api";
import { AccessReviewDetailPage, AccessReviewsPage } from "./AccessReviewsPage";

const SUMMARY = { pending: 2, keep: 1, remove: 0, ended: 0 };
const REVIEW = {
  id: "r1",
  title: "Access review October 2026",
  status: "open",
  due_on: "2026-11-13",
  created_at: "2026-10-30T09:00:00Z",
  started_by_name: "Synthetic Admin",
  completed_at: null,
  completed_by_name: null,
  notes: "",
  summary: SUMMARY,
  version: 3,
};
const item = (id: string, name: string, extra: Record<string, unknown> = {}) => ({
  id,
  person_name: name,
  person_email: `${id}@synthetic.test`,
  account_active: true,
  last_signed_in_at: "2026-10-29T10:00:00Z",
  role_name: "HR / credentialing officer",
  scope: "Main Hospital",
  granted_at: "2026-01-01T00:00:00Z",
  access_ends_at: null,
  decision: "pending",
  decided_by_name: null,
  decided_at: null,
  comment: "",
  is_own: false,
  ...extra,
});
const ITEMS = [
  item("i1", "Hana HR"),
  item("i2", "Synthetic Admin", { is_own: true, role_name: "Organization administrator" }),
  item("i3", "Kept Person", { decision: "keep", decided_by_name: "Synthetic Admin", account_active: false }),
];

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderAt(path: string, grants: string[], overrides: Record<string, unknown> = {}) {
  const fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    if (method === "POST" && url.endsWith("/decide/")) return json([ITEMS[0]]);
    if (method === "POST") return json(REVIEW, url.endsWith("/access-reviews/") ? 201 : 200);
    if (url.includes("/schedule/"))
      return json(
        overrides.schedule ?? {
          interval_days: 90,
          last_completed_at: null,
          next_due_on: "2026-12-01",
          review_due: false,
          open_review_id: null,
          open_review_overdue: false,
        },
      );
    if (url.includes("/items/")) return json(ITEMS);
    if (url.includes("/access-reviews/r1/")) return json(overrides.review ?? REVIEW);
    if (url.includes("/access-reviews/")) return json(overrides.list ?? [REVIEW]);
    return json({});
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
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/access-reviews" element={<AccessReviewsPage />} />
          <Route path="/access-reviews/:id" element={<AccessReviewDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

const posted = (fetchMock: ReturnType<typeof renderAt>, ending: string) =>
  fetchMock.mock.calls.find(([url, init]) => init?.method === "POST" && String(url).endsWith(ending));

describe("AccessReviewsPage (HIMS-IAM-012)", () => {
  afterEach(() => vi.restoreAllMocks());

  it("lists reviews with progress and the next due date", async () => {
    renderAt("/access-reviews", ["access.reviews.view"]);
    expect(await screen.findByRole("link", { name: "Access review October 2026" })).toBeInTheDocument();
    expect(screen.getByText("1 of 3")).toBeInTheDocument();
    expect(await screen.findByText(/Next review due by/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Start a review" })).not.toBeInTheDocument();
  });

  it("starts a review when one is due", async () => {
    const fetchMock = renderAt("/access-reviews", ["access.reviews.view", "access.reviews.manage"], {
      list: [],
      schedule: {
        interval_days: 90,
        last_completed_at: null,
        next_due_on: "2026-10-01",
        review_due: true,
        open_review_id: null,
        open_review_overdue: false,
      },
    });
    expect(await screen.findByText(/A review is due/)).toBeInTheDocument();
    expect(screen.getByText("No access review has been done yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start a review" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Start review" }));
    await vi.waitFor(() => expect(posted(fetchMock, "/access-reviews/")).toBeTruthy(), { timeout: 4000 });
    const body = JSON.parse(String(posted(fetchMock, "/access-reviews/")![1]!.body));
    expect(body.title).toMatch(/^Access review /);
    expect(body.due_on).toBeNull();
  });

  it("keeps one entry and never offers your own access", async () => {
    const fetchMock = renderAt("/access-reviews/r1", ["access.reviews.view", "access.reviews.manage"]);
    expect(await screen.findByText("Hana HR")).toBeInTheDocument();
    expect(screen.getByText("Your own access: another reviewer decides")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Keep Synthetic Admin/ })).not.toBeInTheDocument();
    expect(screen.getByText("Account switched off")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Complete review" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Keep Hana HR HR / credentialing officer Main Hospital" }));
    await vi.waitFor(() => expect(posted(fetchMock, "/decide/")).toBeTruthy(), { timeout: 4000 });
    expect(JSON.parse(String(posted(fetchMock, "/decide/")![1]!.body))).toEqual({
      items: ["i1"],
      decision: "keep",
      comment: "",
    });
  });

  it("removing access needs a reason", async () => {
    const fetchMock = renderAt("/access-reviews/r1", ["access.reviews.view", "access.reviews.manage"]);
    fireEvent.click(
      await screen.findByRole("button", { name: "Remove Hana HR HR / credentialing officer Main Hospital" }),
    );
    const dialog = await screen.findByRole("dialog");
    const submit = within(dialog).getByRole("button", { name: "Remove access now" });
    expect(submit).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText(/Why is the access removed/), {
      target: { value: "Moved to another hospital" },
    });
    fireEvent.click(submit);
    await vi.waitFor(() => expect(posted(fetchMock, "/decide/")).toBeTruthy(), { timeout: 4000 });
    expect(JSON.parse(String(posted(fetchMock, "/decide/")![1]!.body))).toEqual({
      items: ["i1"],
      decision: "remove",
      comment: "Moved to another hospital",
    });
  });

  it("completes a fully decided review with its version", async () => {
    const fetchMock = renderAt("/access-reviews/r1", ["access.reviews.view", "access.reviews.manage"], {
      review: { ...REVIEW, summary: { pending: 0, keep: 3, remove: 0, ended: 0 } },
    });
    fireEvent.click(await screen.findByRole("button", { name: "Complete review" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Complete review" }));
    await vi.waitFor(() => expect(posted(fetchMock, "/complete/")).toBeTruthy(), { timeout: 4000 });
    expect(JSON.parse(String(posted(fetchMock, "/complete/")![1]!.body))).toEqual({ version: 3, notes: "" });
  });

  it("auditors can read and download but not decide", async () => {
    renderAt("/access-reviews/r1", ["access.reviews.view"]);
    expect(await screen.findByText("Hana HR")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Download (CSV)" })).toHaveAttribute(
      "href",
      "/api/v1/access-reviews/r1/export/",
    );
    expect(screen.queryByRole("button", { name: /^Keep / })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Complete review" })).not.toBeInTheDocument();
  });
});
