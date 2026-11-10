"use client";
import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";

/** Tenant-scoped fetch with loading/error states. Re-run via `reload()`. */
export function useTenantApi<T>(buildPath: (tenant: string) => string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState<number | null>(null);
  const [tenant, setTenant] = useState<string | null>(null);

  const load = useCallback(() => {
    const t = getSelectedTenant();
    setTenant(t);
    if (!t) {
      setLoading(false);
      return;
    }
    const path = buildPath(t);
    if (!path) {
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .get<T>(path, t)
      .then((d) => {
        setData(d);
        setError("");
        setStatus(null);
      })
      .catch((e: Error & { status?: number }) => {
        setError(e.message);
        setStatus(typeof e.status === "number" ? e.status : null);
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(load, [load]);
  return { data, loading, error, status, setError, reload: load, tenant };
}

/** Platform-scoped fetch: no tenant selector, no X-Tenant header.
 * Server re-checks `is_platform_admin` on every call. */
export function usePlatformApi<T>(path: string | null, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [status, setStatus] = useState<number | null>(null);

  const load = useCallback(() => {
    if (!path) {
      setLoading(false);
      return;
    }
    setLoading(true);
    api
      .get<T>(path)
      .then((d) => {
        setData(d);
        setError("");
        setStatus(null);
      })
      .catch((e: Error & { status?: number }) => {
        setError(e.message);
        setStatus(typeof e.status === "number" ? e.status : null);
      })
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(load, [load]);
  return { data, loading, error, status, setError, reload: load };
}

/** Today's local date as YYYY-MM-DD for date inputs. */
export function todayInput(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
