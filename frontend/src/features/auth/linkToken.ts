import { useEffect, useState } from "react";

/**
 * Activation and password-reset links look like `/activate#token=...` and
 * `/reset-password#token=...`. The fragment is never sent to any server (spec 29.1), so we read
 * it in the browser and then remove it from the address bar and history.
 */
export function takeLinkTokenFromUrl(): string | null {
  const params = new URLSearchParams(window.location.hash.replace(/^#/, ""));
  const token = params.get("token");
  if (token) {
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
  }
  return token;
}

/**
 * The link's token, also when a newer link is pasted into the same tab: only the part after `#`
 * changes then, so the browser does not reload the page (found by the browser tests,
 * HIMS-QA-001). Without this, a person who first opened an old link stayed on "link not valid".
 */
export function useLinkToken(): string | null {
  const [token, setToken] = useState(takeLinkTokenFromUrl);
  useEffect(() => {
    const onHashChange = () => {
      const next = takeLinkTokenFromUrl();
      if (next) setToken(next);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);
  return token;
}
