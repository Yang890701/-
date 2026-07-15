export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export type ApiUser = {
  id: number;
  username: string;
  role: string;
};

export type LoginResponse = {
  access_token: string;
  token_type: string;
  user: ApiUser;
};

export type RefreshResponse = {
  access_token: string;
  token_type: string;
};

type AuthHandlers = {
  getAccessToken: () => string | null;
  setAccessToken: (token: string | null) => void;
  onUnauthorized: () => void;
};

let authHandlers: AuthHandlers = {
  getAccessToken: () => null,
  setAccessToken: () => undefined,
  onUnauthorized: () => {
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  },
};

let refreshPromise: Promise<string | null> | null = null;

export function configureApiAuth(handlers: AuthHandlers) {
  authHandlers = handlers;
}

function apiUrl(path: string) {
  return `${API_BASE}${path}`;
}

function authHeaders(headers?: HeadersInit) {
  const nextHeaders = new Headers(headers);
  const token = authHandlers.getAccessToken();
  if (token) {
    nextHeaders.set("Authorization", `Bearer ${token}`);
  }
  return nextHeaders;
}

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = fetch(apiUrl("/api/auth/refresh"), {
      method: "POST",
      credentials: "include",
    })
      .then(async (response) => {
        if (!response.ok) {
          return null;
        }
        const body = (await response.json()) as RefreshResponse;
        authHandlers.setAccessToken(body.access_token);
        return body.access_token;
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

export async function apiFetch(
  path: string,
  init: RequestInit = {},
  retry = true,
): Promise<Response> {
  const response = await fetch(apiUrl(path), {
    ...init,
    headers: authHeaders(init.headers),
    credentials: init.credentials ?? "include",
  });

  if (response.status !== 401 || !retry) {
    return response;
  }

  const token = await refreshAccessToken();
  if (!token) {
    authHandlers.setAccessToken(null);
    authHandlers.onUnauthorized();
    return response;
  }

  return apiFetch(path, init, false);
}

export async function apiJson<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) {
    headers.set("Content-Type", "application/json");
  }

  const response = await apiFetch(path, { ...init, headers });
  if (!response.ok) {
    const message = await response
      .json()
      .then((body) => body.detail ?? "API request failed")
      .catch(() => "API request failed");
    throw new Error(String(message));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

export async function login(username: string, password: string): Promise<LoginResponse> {
  const response = await fetch(apiUrl("/api/auth/login"), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  if (!response.ok) {
    const message = await response
      .json()
      .then((body) => body.detail ?? "登入失敗")
      .catch(() => "登入失敗");
    throw new Error(String(message));
  }
  return (await response.json()) as LoginResponse;
}

export function filenameFromContentDisposition(header: string | null, fallback: string) {
  if (!header) {
    return fallback;
  }
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (utf8?.[1]) {
    return decodeURIComponent(utf8[1]);
  }
  const basic = /filename="?([^"]+)"?/i.exec(header);
  return basic?.[1] ?? fallback;
}
