// Use same-origin proxy to avoid CORS; proxy forwards to backend (see app/api/proxy/[[...path]]/route.ts)
const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "/api/proxy";
const REQUEST_TIMEOUT_MS = 35_000;

export type ApiError = { detail: string };

async function request<T>(
  path: string,
  options: RequestInit & { token?: string | null } = {}
): Promise<T> {
  const { token, ...init } = options;
  const headers: Record<string, string> = { ...(init.headers as Record<string, string>) };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (init.body) {
    if (init.body instanceof URLSearchParams) {
      headers["Content-Type"] = "application/x-www-form-urlencoded";
    } else if (typeof init.body === "string") {
      headers["Content-Type"] = "application/json";
    }
  }
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers, signal: controller.signal });
  } catch (err) {
    clearTimeout(timeoutId);
    if (err instanceof Error) {
      if (err.name === "AbortError") {
        throw new Error(`Request timed out. Is the API running at ${API_BASE}?`);
      }
      throw new Error(err.message || "Could not reach the API. Check that the backend is running.");
    }
    throw err;
  }
  clearTimeout(timeoutId);
  if (!res.ok) {
    const err: ApiError = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string, token?: string | null) =>
    request<T>(path, { method: "GET", token }),
  post: <T>(path: string, body: unknown, token?: string | null) =>
    request<T>(path, {
      method: "POST",
      body: body instanceof URLSearchParams ? body : JSON.stringify(body),
      token,
    }),
  patch: <T>(path: string, body: unknown, token?: string | null) =>
    request<T>(path, {
      method: "PATCH",
      body: body instanceof URLSearchParams ? body : JSON.stringify(body),
      token,
    }),
};

export { API_BASE };
