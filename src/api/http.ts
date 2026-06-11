/* Thin fetch wrapper: base path, bearer token, JSON, typed errors. */

const BASE = '/api/v1';
const TOKEN_KEY = 'agentforge.token';

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/* Token change subscription so React can re-render on login/logout
   (localStorage alone fires no event in the same tab). */
const tokenListeners = new Set<() => void>();
export function subscribeToken(listener: () => void): () => void {
  tokenListeners.add(listener);
  return () => tokenListeners.delete(listener);
}

export function setToken(token: string | null): void {
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else localStorage.removeItem(TOKEN_KEY);
  tokenListeners.forEach((fn) => fn());
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(BASE + path, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = (data as { detail?: string }).detail ?? detail;
    } catch {
      /* ignore */
    }
    // a dead/expired token must not linger and loop forever
    if (res.status === 401) setToken(null);
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body),
  patch: <T>(path: string, body?: unknown) => request<T>('PATCH', path, body),
  base: BASE,
};
