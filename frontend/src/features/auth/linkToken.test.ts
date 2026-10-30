import { takeLinkTokenFromUrl } from "./linkToken";

describe("takeLinkTokenFromUrl", () => {
  it("reads the token from the fragment and removes it from the address bar", () => {
    window.history.replaceState(null, "", "/activate#token=abc%3A123");
    expect(takeLinkTokenFromUrl()).toBe("abc:123");
    expect(window.location.hash).toBe("");
    expect(window.location.pathname).toBe("/activate");
  });

  it("returns null when there is no token", () => {
    window.history.replaceState(null, "", "/activate");
    expect(takeLinkTokenFromUrl()).toBeNull();
  });
});

describe("useLinkToken", () => {
  it("picks up a newer link pasted into the same tab", async () => {
    const { renderHook, act } = await import("@testing-library/react");
    const { useLinkToken } = await import("./linkToken");
    window.history.replaceState(null, "", "/activate#token=old");
    const { result } = renderHook(() => useLinkToken());
    expect(result.current).toBe("old");
    act(() => {
      window.history.replaceState(null, "", "/activate#token=new");
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(result.current).toBe("new");
    expect(window.location.hash).toBe("");
  });
});
