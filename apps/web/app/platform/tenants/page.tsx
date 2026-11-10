"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  LoadingState,
  PageHeader,
  Pagination,
  Select,
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
import {
  usePlatformMe,
  type PlatformTenantItem,
  type PlatformTenantList,
} from "@/lib/platform";
import { Shell } from "../../shell";

const PAGE_SIZE = 20;
const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "active", label: "Active" },
  { value: "suspended", label: "Suspended" },
  { value: "deactivated", label: "Deactivated" },
];

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString();
}

export default function PlatformTenantsPage() {
  const gate = usePlatformMe();
  const [filter, setFilter] = useState("");
  const [items, setItems] = useState<PlatformTenantItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [fetchStatus, setFetchStatus] = useState<number | null>(null);

  const loadPage = useCallback(
    async (nextOffset: number, append: boolean) => {
      const qs = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(nextOffset),
      });
      if (filter) qs.set("status", filter);
      if (!append) setLoading(true);
      else setLoadingMore(true);
      try {
        const page = await api.get<PlatformTenantList>(
          `/api/v1/platform/tenants?${qs.toString()}`,
        );
        setItems((prev) => (append ? [...prev, ...page.items] : page.items));
        setTotal(page.total);
        setError("");
        setFetchStatus(null);
      } catch (e) {
        const err = e as Error & { status?: number };
        setError(err.message);
        setFetchStatus(typeof err.status === "number" ? err.status : null);
        if (!append) {
          setItems([]);
          setTotal(0);
        }
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [filter],
  );

  useEffect(() => {
    if (gate.loading || !gate.isPlatformAdmin) return;
    setItems([]);
    setTotal(0);
    void loadPage(0, false);
  }, [gate.loading, gate.isPlatformAdmin, loadPage]);

  const forbidden = fetchStatus === 403;
  const unauthenticated = gate.status === 401;

  return (
    <Shell>
      <PageHeader
        title="Platform tenants"
        description="Read-only workspace directory. Tenant status and subscription status are separate domains."
      />
      {gate.loading ? (
        <LoadingState label="Checking platform access" />
      ) : unauthenticated || !gate.me ? (
        <Card title="Sign in required">
          <EmptyState title="You are not signed in">
            <Link href="/login">Sign in</Link> with a platform administrator account.
          </EmptyState>
        </Card>
      ) : !gate.isPlatformAdmin || forbidden ? (
        <Alert tone="danger" title="Platform access required">
          This console is limited to platform administrators. clinical and tenant
          routes remain governed by membership and permissions.
        </Alert>
      ) : error && !loading ? (
        <Alert tone="danger" title="Something went wrong">
          {error}{" "}
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              setItems([]);
              void loadPage(0, false);
            }}
          >
            Retry
          </Button>
        </Alert>
      ) : loading ? (
        <LoadingState label="Loading workspaces" />
      ) : items.length === 0 ? (
        <>
          <Card title="Filter">
            <Field label="Tenant status" htmlFor="platform-status-filter">
              {() => (
                <Select
                  id="platform-status-filter"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  options={STATUS_OPTIONS}
                />
              )}
            </Field>
          </Card>
          <EmptyState title="No workspaces">
            {filter ? "No workspaces with this tenant status." : "No workspaces yet."}
          </EmptyState>
        </>
      ) : (
        <>
          <Card title="Filter">
            <Field label="Tenant status" htmlFor="platform-status-filter">
              {() => (
                <Select
                  id="platform-status-filter"
                  value={filter}
                  onChange={(e) => setFilter(e.target.value)}
                  options={STATUS_OPTIONS}
                />
              )}
            </Field>
          </Card>
          <Card title="Workspaces">
            <Table
              caption="Workspaces"
              density="compact"
              columns={
                <>
                  <Th>Workspace</Th>
                  <Th>Tenant status</Th>
                  <Th>Plan</Th>
                  <Th>Subscription status</Th>
                  <Th>Trial ends</Th>
                  <Th>Specialties</Th>
                </>
              }
            >
              {items.map((t) => (
                <tr key={t.id}>
                  <Td>
                    <Link href={`/platform/tenants/${t.id}`}>{t.name}</Link>
                    <br />
                    <span className="hos-helper">{t.slug}</span>
                  </Td>
                  <Td>
                    <Status value={t.status} />
                  </Td>
                  <Td>{t.subscription ? t.subscription.plan_name || t.subscription.plan_code : "—"}</Td>
                  <Td>
                    {t.subscription ? <Status value={t.subscription.status} /> : "—"}
                  </Td>
                  <Td>{t.subscription ? formatDate(t.subscription.trial_ends_at) : "—"}</Td>
                  <Td>{t.specialties_enabled.join(", ") || "—"}</Td>
                </tr>
              ))}
            </Table>
            <Pagination
              label={`Showing ${items.length} of ${total}`}
              hasMore={items.length < total}
              pending={loadingMore}
              onMore={() => void loadPage(items.length, true)}
            />
          </Card>
          <p className="hos-helper">
            Owner information and location or membership counts are intentionally
            not exposed in this read-only phase.
          </p>
        </>
      )}
    </Shell>
  );
}
