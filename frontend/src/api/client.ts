/**
 * HTTP client for the HIMS API.
 *
 * - Session cookie auth; CSRF token echoed from the `hims_csrftoken` cookie on unsafe methods.
 * - Every request carries an `X-Request-ID` so failures can be traced end to end (spec 29.1).
 * - Errors are RFC 9457 problem documents, surfaced as `ApiError`.
 * - Never put PHI in paths or query strings that are not required by the API contract.
 */

export const API_BASE = "/api/v1";
// Must match the backend's HIMS_CSRF_COOKIE_NAME (differs per local deployment, e.g. US).
const CSRF_COOKIE: string = import.meta.env.VITE_CSRF_COOKIE ?? "hims_csrftoken";

export interface ProblemFieldError {
  field: string | null;
  message: string;
  code: string;
}

export interface Problem {
  type?: string;
  title: string;
  status: number;
  detail?: string;
  code: string;
  request_id?: string | null;
  errors?: ProblemFieldError[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly problem: Problem;

  constructor(status: number, problem: Problem) {
    super(problem.detail ?? problem.title);
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
  }

  get code(): string {
    return this.problem.code;
  }
}

export function readCookie(name: string): string | null {
  const prefix = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const trimmed = part.trim();
    if (trimmed.startsWith(prefix)) return decodeURIComponent(trimmed.slice(prefix.length));
  }
  return null;
}

type Method = "GET" | "POST" | "PATCH";

export interface RequestOptions {
  body?: unknown;
  query?: Record<string, string | number | undefined>;
  /** Send for create/submit operations so retries never duplicate work (spec 29.3). */
  idempotencyKey?: string;
  signal?: AbortSignal;
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = `${API_BASE}${path}`;
  if (!query) return url;
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const qs = params.toString();
  return qs ? `${url}?${qs}` : url;
}

export async function apiRequest<T>(
  method: Method,
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: "application/json",
    "X-Request-ID": crypto.randomUUID(),
  };
  // FormData (file uploads) sets its own multipart Content-Type with the boundary.
  const isForm = options.body instanceof FormData;
  if (options.body !== undefined && !isForm) headers["Content-Type"] = "application/json";
  if (method !== "GET") {
    const token = readCookie(CSRF_COOKIE);
    if (token) headers["X-CSRFToken"] = token;
  }
  if (options.idempotencyKey) headers["Idempotency-Key"] = options.idempotencyKey;

  const response = await fetch(buildUrl(path, options.query), {
    method,
    headers,
    body:
      options.body === undefined
        ? undefined
        : isForm
          ? (options.body as FormData)
          : JSON.stringify(options.body),
    credentials: "same-origin",
    signal: options.signal,
  });

  if (response.status === 204) return undefined as T;
  const isJson = (response.headers.get("Content-Type") ?? "").includes("json");
  const payload: unknown = isJson ? await response.json() : null;

  if (!response.ok) {
    const problem = (payload as Problem | null) ?? {
      title: response.statusText || "Request failed",
      status: response.status,
      code: "HTTP_ERROR",
    };
    throw new ApiError(response.status, problem);
  }
  return payload as T;
}

export const api = {
  get: <T>(path: string, options?: Omit<RequestOptions, "body">) =>
    apiRequest<T>("GET", path, options),
  post: <T>(path: string, body?: unknown, options?: Omit<RequestOptions, "body">) =>
    apiRequest<T>("POST", path, { ...options, body }),
  patch: <T>(path: string, body: unknown, options?: Omit<RequestOptions, "body">) =>
    apiRequest<T>("PATCH", path, { ...options, body }),
};

export function isUnauthenticated(error: unknown): boolean {
  return error instanceof ApiError && error.status === 401;
}
