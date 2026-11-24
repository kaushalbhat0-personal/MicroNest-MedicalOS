"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import {
  Alert,
  Badge,
  Breadcrumbs,
  Card,
  EmptyState,
  LoadingState,
  PageHeader,
  Status,
  Table,
  Td,
  Th,
} from "@healthcare-os/ui";
import { usePlatformMe, type PlatformTenantItem } from "@/lib/platform";
import { usePlatformApi } from "@/lib/use-api";
import { Shell } from "../../../shell";

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString();
}

function formatDateTime(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString();
}

function readinessBadge(specialty: { maturity: string; ready_for_use: boolean }) {
  if (specialty.ready_for_use) return <Badge tone="success">Ready</Badge>;
  if (specialty.maturity === "discovery") return <Badge tone="warning">Discovery only</Badge>;
  return <Badge tone="neutral">Unknown</Badge>;
}

export default function PlatformTenantDetailPage() {
  const params = useParams();
  const id = typeof params.id === "string" ? params.id : "";
  const gate = usePlatformMe();
  const detail = usePlatformApi<PlatformTenantItem>(
    gate.isPlatformAdmin && id ? `/api/v1/platform/tenants/${id}` : null,
    [gate.isPlatformAdmin, id],
  );

  const unauthenticated = gate.status === 401;
  const forbidden = detail.status === 403;
  const notFound = detail.status === 404;

  return (
    <Shell>
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
          This console is limited to platform administrators.
        </Alert>
      ) : detail.loading ? (
        <LoadingState label="Loading workspace" />
      ) : detail.error && !notFound ? (
        <Alert tone="danger" title="Something went wrong">
          {detail.error}{" "}
          <Link href="/platform/tenants">Back to directory</Link>
        </Alert>
      ) : notFound || !detail.data ? (
        <Card title="Workspace">
          <EmptyState title="Workspace not found">
            <Link href="/platform/tenants">Back to directory</Link>
          </EmptyState>
        </Card>
      ) : (
        <>
          <Breadcrumbs
            items={[{ label: "Platform tenants", href: "/platform/tenants" }, { label: detail.data.name }]}
          />
          <PageHeader
            title={detail.data.name}
            description={`Workspace detail · ${detail.data.slug}`}
            actions={<Link href="/platform/tenants">Directory</Link>}
          />
          <Card title="Workspace identity">
            <Table
              caption="Workspace identity"
              columns={
                <>
                  <Th>Field</Th>
                  <Th>Value</Th>
                </>
              }
            >
              <tr>
                <Td>Tenant status</Td>
                  <Td>
                    <Status value={detail.data.status} />
                  </Td>
                </tr>
                <tr>
                  <Td>Created</Td>
                  <Td>{formatDateTime(detail.data.created_at)}</Td>
                </tr>
              <tr>
                <Td>Updated</Td>
                <Td>{formatDateTime(detail.data.updated_at)}</Td>
              </tr>
            </Table>
            <p className="hos-helper">
              Tenant status describes the workspace account. Subscription status
              below is a separate commercial domain.
            </p>
          </Card>
          <Card title="Subscription (read-only)">
            {detail.data.subscription ? (
              <Table
                caption="Subscription"
                columns={
                  <>
                    <Th>Field</Th>
                    <Th>Value</Th>
                  </>
                }
              >
                <tr>
                  <Td>Plan</Td>
                    <Td>
                      {detail.data.subscription.plan_name || detail.data.subscription.plan_code}{" "}
                      <span className="hos-helper">({detail.data.subscription.plan_code})</span>
                    </Td>
                  </tr>
                  <tr>
                    <Td>Subscription status</Td>
                    <Td>
                      <Status value={detail.data.subscription.status} />{" "}
                      <Badge tone={detail.data.subscription.is_in_trial ? "success" : "neutral"}>
                        {detail.data.subscription.is_in_trial ? "In trial" : "Not in trial"}
                      </Badge>
                    </Td>
                  </tr>
                  <tr>
                    <Td>Trial period</Td>
                    <Td>
                      {formatDate(detail.data.subscription.trial_starts_at)} →{" "}
                      {formatDate(detail.data.subscription.trial_ends_at)}
                    </Td>
                  </tr>
                  <tr>
                    <Td>Plan limits</Td>
                    <Td>
                      {detail.data.subscription.limits
                        ? `${detail.data.subscription.limits.max_locations} locations · ${detail.data.subscription.limits.max_practitioners} practitioners · ${detail.data.subscription.limits.max_staff_seats} seats`
                        : "—"}{" "}
                      <span className="hos-helper">(capacity enforced for seats/locations/practitioners)</span>
                    </Td>
                  </tr>
              </Table>
            ) : (
              <EmptyState title="No subscription record" />
            )}
            <p className="hos-helper">
              Each view of this workspace is recorded in its own audit trail.
            </p>
          </Card>
          <Card title="Specialties">
            {detail.data.specialties.length === 0 ? (
              <EmptyState title="No specialties enabled" />
            ) : (
              <Table
                caption="Enabled specialties"
                columns={
                  <>
                    <Th>Specialty</Th>
                    <Th>Pack version</Th>
                    <Th>Readiness</Th>
                  </>
                }
              >
                {detail.data.specialties.map((s) => (
                  <tr key={s.code}>
                    <Td>{s.code}</Td>
                    <Td>{s.pack_version}</Td>
                    <Td>{readinessBadge(s)}</Td>
                  </tr>
                ))}
              </Table>
            )}
            <p className="hos-helper">
              Discovery-only specialties are never operational workflows. Owner
              information is not exposed in this read-only phase.
            </p>
          </Card>
        </>
      )}
    </Shell>
  );
}
