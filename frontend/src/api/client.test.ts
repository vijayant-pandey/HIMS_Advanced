import { ApiError, api } from "./client";

function jsonResponse(status: number, body: unknown, contentType = "application/json") {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": contentType } });
}

describe("api client", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.cookie = "hims_csrftoken=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
  });

  it("sends request id, CSRF token and idempotency key on writes", async () => {
    document.cookie = "hims_csrftoken=csrf-123";
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse(201, { id: "f1" }));

    await api.post("/facilities/", { code: "a" }, { idempotencyKey: "key-12345678" });

    const [url, init] = fetchMock.mock.calls[0]!;
    const headers = init!.headers as Record<string, string>;
    expect(url).toBe("/api/v1/facilities/");
    expect(headers["X-CSRFToken"]).toBe("csrf-123");
    expect(headers["Idempotency-Key"]).toBe("key-12345678");
    expect(headers["X-Request-ID"]).toMatch(/^[0-9a-f-]{36}$/);
  });

  it("raises ApiError carrying the problem document", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(
      jsonResponse(
        409,
        { title: "Conflict", status: 409, code: "STALE_RESOURCE", request_id: "r-1" },
        "application/problem+json",
      ),
    );

    const error = await api.get("/facilities/x/").catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).code).toBe("STALE_RESOURCE");
    expect((error as ApiError).problem.request_id).toBe("r-1");
  });

  it("omits empty query parameters", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(jsonResponse(200, { results: [] }));
    await api.get("/staff/", { query: { search: "", page: 2 } });
    expect(fetchMock.mock.calls[0]![0]).toBe("/api/v1/staff/?page=2");
  });
});
