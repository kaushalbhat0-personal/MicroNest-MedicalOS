const API = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type ApiError = { type: string; title: string; status: number; detail: string };

async function request<T>(path: string, init: RequestInit, tenantId?: string): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (tenantId) headers["X-Tenant"] = tenantId;
  const res = await fetch(`${API}${path}`, {
    ...init,
    headers: { ...headers, ...(init.headers as Record<string, string>) },
    credentials: "include",
  });
  if (res.status === 204) return undefined as T;
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const err = new Error((body as ApiError).detail ?? `request failed: ${res.status}`) as Error & {
      status: number;
    };
    err.status = res.status;
    throw err;
  }
  return body as T;
}

export const api = {
  get: <T>(path: string, tenantId?: string) => request<T>(path, { method: "GET" }, tenantId),
  post: <T>(path: string, payload?: unknown, tenantId?: string) =>
    request<T>(path, { method: "POST", body: JSON.stringify(payload ?? {}) }, tenantId),
  patch: <T>(path: string, payload?: unknown, tenantId?: string) =>
    request<T>(path, { method: "PATCH", body: JSON.stringify(payload ?? {}) }, tenantId),
  del: <T>(path: string, tenantId?: string) => request<T>(path, { method: "DELETE" }, tenantId),
};

export type TenantOption = { id: string; slug: string; name: string };
export type Me = {
  id: string;
  email: string;
  display_name: string;
  is_platform_admin: boolean;
  tenants: TenantOption[];
};
