import { getApiBaseUrl, getClientInstanceId } from "./config";
import { apiRequest, parseBody } from "./http";
import { SecureTokenStore } from "./secureStore";

export type TenantOption = { id: string; slug: string; name: string };

export type NativeTokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
  id: string;
  email: string;
  display_name: string;
  is_platform_admin: boolean;
  email_verified: boolean;
  tenants: TenantOption[];
  session_id: string;
  client_platform: string;
};

export type WorkspaceContext = {
  tenant_id: string;
  membership_id: string;
  role: string;
  permissions: string[];
  location_ids: string[];
};

export type MeResponse = {
  id: string;
  email: string;
  display_name: string;
  is_platform_admin: boolean;
  email_verified: boolean;
  tenants: TenantOption[];
};

/** In-memory access token only — never persisted to disk or web storage. */
let accessToken: string | null = null;
let accessExpiresAt = 0;
let refreshInFlight: Promise<NativeTokenResponse> | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function clearAccessToken(): void {
  accessToken = null;
  accessExpiresAt = 0;
}

function applyTokens(body: NativeTokenResponse): void {
  accessToken = body.access_token;
  accessExpiresAt = Date.now() + Math.max(30, body.expires_in - 30) * 1000;
}

function stripTokensForUi(body: NativeTokenResponse): Omit<
  NativeTokenResponse,
  "access_token" | "refresh_token"
> & { access_token?: undefined; refresh_token?: undefined } {
  const { access_token: _a, refresh_token: _r, ...rest } = body;
  return rest;
}

export type PublicSession = ReturnType<typeof stripTokensForUi>;

export async function nativeLogin(
  email: string,
  password: string,
): Promise<PublicSession> {
  const instanceId = await getClientInstanceId();
  const res = await apiRequest("POST", "/api/v1/auth/native/login", {}, {
    email,
    password,
    client_platform: "windows",
    device_label: "HealthcareOS-Desktop",
    client_instance_id: instanceId,
  });
  const body = parseBody<NativeTokenResponse>(res);
  if (res.status !== 200 || !body?.access_token) {
    throw new Error("login_failed");
  }
  applyTokens(body);
  await SecureTokenStore.storeRefreshToken(body.refresh_token);
  return stripTokensForUi(body);
}

export async function nativeRefresh(): Promise<NativeTokenResponse> {
  if (refreshInFlight) return refreshInFlight;
  refreshInFlight = (async () => {
    const refresh = await SecureTokenStore.retrieveRefreshToken();
    if (!refresh) throw new Error("no_refresh");
    const res = await apiRequest("POST", "/api/v1/auth/native/refresh", {}, {
      refresh_token: refresh,
    });
    const body = parseBody<NativeTokenResponse>(res);
    if (res.status !== 200 || !body?.access_token) {
      await SecureTokenStore.clearSession();
      clearAccessToken();
      throw new Error("refresh_failed");
    }
    applyTokens(body);
    await SecureTokenStore.storeRefreshToken(body.refresh_token);
    return body;
  })();
  try {
    return await refreshInFlight;
  } finally {
    refreshInFlight = null;
  }
}

export async function nativeLogout(): Promise<{ backendOk: boolean }> {
  const token = accessToken;
  let backendOk = false;
  try {
    if (token) {
      const res = await apiRequest(
        "POST",
        "/api/v1/auth/native/logout",
        { Authorization: `Bearer ${token}` },
      );
      backendOk = res.status === 204 || res.status === 200;
    }
  } catch {
    backendOk = false;
  } finally {
    clearAccessToken();
    try {
      await SecureTokenStore.clearSession();
    } catch {
      // Local cleanup best-effort when DPAPI fails.
    }
  }
  return { backendOk };
}

export async function ensureAccessToken(): Promise<string> {
  if (accessToken && Date.now() < accessExpiresAt) return accessToken;
  const body = await nativeRefresh();
  return body.access_token;
}

export async function apiFetch(
  path: string,
  init: { method?: string; tenantId?: string; body?: unknown } = {},
): Promise<{ status: number; json: unknown }> {
  const token = await ensureAccessToken();
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
  };
  if (init.tenantId) headers["X-Tenant"] = init.tenantId;
  const res = await apiRequest(init.method ?? "GET", path, headers, init.body);
  if (res.status === 401) {
    // One refresh attempt, then fail (no loop).
    try {
      const token2 = (await nativeRefresh()).access_token;
      headers.Authorization = `Bearer ${token2}`;
      const retry = await apiRequest(init.method ?? "GET", path, headers, init.body);
      return { status: retry.status, json: parseBody(retry) };
    } catch {
      clearAccessToken();
      return { status: 401, json: null };
    }
  }
  return { status: res.status, json: parseBody(res) };
}

export async function tryRestoreSession(): Promise<PublicSession | null> {
  try {
    const body = await nativeRefresh();
    return stripTokensForUi(body);
  } catch {
    clearAccessToken();
    return null;
  }
}

export async function fetchMe(tenantId?: string): Promise<MeResponse> {
  const res = await apiFetch("/api/v1/auth/me", { tenantId });
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status !== 200 || !res.json) throw new Error("me_failed");
  return res.json as MeResponse;
}

export async function fetchWorkspaceContext(
  tenantId: string,
): Promise<WorkspaceContext> {
  const res = await apiFetch(`/api/v1/tenants/${tenantId}/workspace-context`, {
    tenantId,
  });
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status !== 200 || !res.json) throw new Error("workspace_failed");
  return res.json as WorkspaceContext;
}

export async function probeHealth(): Promise<boolean> {
  try {
    const base = await getApiBaseUrl();
    const res = await apiRequest("GET", `${base}/api/healthz`, {});
    return res.status === 200;
  } catch {
    return false;
  }
}

export type OpsDashboard = {
  tenant_id: string;
  location_id: string;
  location_name: string;
  service_date: string;
  appointments: {
    scheduled_today: number;
    waiting: number;
    checked_in: number;
    in_consultation: number;
    completed: number;
    cancelled: number;
    no_show: number;
  } | null;
  reception: {
    scheduled_today: number;
    waiting: number;
    checked_in: number;
    completed: number;
  } | null;
  follow_ups: {
    due_today: number;
    overdue: number;
    upcoming: number;
  } | null;
  billing: {
    outstanding_invoice_count: number;
    outstanding_amount: string;
    currency: string;
    payments_today_count: number;
    payments_today_amount: string;
  } | null;
  todays_appointments: Array<{
    id: string;
    start_at: string;
    end_at: string;
    status: string;
    patient_display_name: string;
    practitioner_display_name: string;
    queue_token: number | null;
  }>;
  sections_omitted: string[];
};

export async function fetchOperationsDashboard(
  tenantId: string,
  locationId: string,
): Promise<OpsDashboard | null> {
  const res = await apiFetch(
    `/api/v1/tenants/${tenantId}/locations/${locationId}/operations-dashboard`,
    { tenantId },
  );
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) return null;
  if (res.status !== 200 || !res.json) return null;
  return res.json as OpsDashboard;
}

export async function fetchTenantLocations(
  tenantId: string,
): Promise<Array<{ id: string; name: string }>> {
  const res = await apiFetch(`/api/v1/tenants/${tenantId}/locations`, { tenantId });
  if (res.status !== 200 || !res.json) return [];
  const data = res.json as Array<{ id: string; name: string }>;
  return Array.isArray(data) ? data.map((l) => ({ id: l.id, name: l.name })) : [];
}
