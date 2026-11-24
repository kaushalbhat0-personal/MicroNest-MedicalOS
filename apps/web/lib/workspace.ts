import { api } from "@/lib/api";

export type WorkspaceContext = {
  tenant_id: string;
  membership_id: string;
  role: string;
  permissions: string[];
  location_ids: string[];
};

type CacheEntry = { ctx: WorkspaceContext; fetchedAt: number };

const CACHE_TTL_MS = 60_000;
const cache = new Map<string, CacheEntry>();
const inflight = new Map<string, Promise<WorkspaceContext>>();

export function clearWorkspaceContextCache(tenantId?: string): void {
  if (tenantId) {
    cache.delete(tenantId);
    inflight.delete(tenantId);
  } else {
    cache.clear();
    inflight.clear();
  }
}

export async function fetchWorkspaceContext(tenantId: string): Promise<WorkspaceContext> {
  const hit = cache.get(tenantId);
  if (hit && Date.now() - hit.fetchedAt < CACHE_TTL_MS) {
    return hit.ctx;
  }
  const pending = inflight.get(tenantId);
  if (pending) return pending;

  const req = api
    .get<WorkspaceContext>(`/api/v1/tenants/${tenantId}/workspace-context`, tenantId)
    .then((ctx) => {
      cache.set(tenantId, { ctx, fetchedAt: Date.now() });
      inflight.delete(tenantId);
      return ctx;
    })
    .catch((err) => {
      inflight.delete(tenantId);
      throw err;
    });
  inflight.set(tenantId, req);
  return req;
}
