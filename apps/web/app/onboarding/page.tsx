"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  LoadingState,
  PageHeader,
  Select,
  Status,
} from "@healthcare-os/ui";
import { api, type Me } from "@/lib/api";
import { clearWorkspaceContextCache } from "@/lib/workspace";
import { getSelectedTenant, setSelectedTenant } from "@/lib/tenant";
import { Shell } from "../shell";

type WorkspaceResponse = {
  tenant: { id: string; name: string; slug: string; status: string };
  location: { id: string; name: string; timezone: string };
  membership: { id: string; role: string };
  practitioner: { id: string; display_name: string };
  specialties_enabled: string[];
  subscription: { status: string; trial_ends_at: string | null; plan_code: string };
};

type VerificationRow = {
  practitioner_id: string;
  display_name: string;
  status: string;
  reason: string | null;
};

const SPECIALTIES = [
  { value: "dental", label: "Dental" },
  { value: "ophthalmology", label: "Ophthalmology (generic clinic for pilot discovery)" },
];

const STEPS = [
  "Create workspace",
  "Review clinic",
  "Practitioner approval",
  "Invite staff",
  "Open dashboard",
] as const;

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return "00000000-0000-4000-8000-000000000000";
}

export default function OnboardingPage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [created, setCreated] = useState<WorkspaceResponse | null>(null);
  const [verifications, setVerifications] = useState<VerificationRow[]>([]);
  const [verifyLoading, setVerifyLoading] = useState(false);

  const [clinicName, setClinicName] = useState("");
  const [slug, setSlug] = useState("");
  const [locationName, setLocationName] = useState("Main Clinic");
  const [timezone, setTimezone] = useState("Asia/Kolkata");
  const [practitionerName, setPractitionerName] = useState("");
  const [specialty, setSpecialty] = useState("dental");
  const [idemKey] = useState(() => newIdempotencyKey());

  useEffect(() => {
    api
      .get<Me>("/api/v1/auth/me")
      .then((m) => {
        setMe(m);
        if (!practitionerName) setPractitionerName(m.display_name);
        if (m.tenants.length > 0 && !created) {
          // Resume: existing workspace owners start at review/approval.
          setStep(1);
          const tid = getSelectedTenant() ?? m.tenants[0].id;
          setSelectedTenant(tid);
        }
      })
      .catch(() => router.push("/login"));
  }, [router, created, practitionerName]);

  useEffect(() => {
    if (clinicName && !slug) {
      setSlug(
        clinicName
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-|-$/g, "")
          .slice(0, 60),
      );
    }
  }, [clinicName, slug]);

  const tenantId = created?.tenant.id ?? getSelectedTenant();

  async function loadVerifications(tid: string) {
    setVerifyLoading(true);
    setError("");
    try {
      const rows = await api.get<VerificationRow[]>(`/api/v1/tenants/${tid}/verification`, tid);
      setVerifications(rows);
    } catch (e) {
      setError((e as Error).message);
      setVerifications([]);
    } finally {
      setVerifyLoading(false);
    }
  }

  useEffect(() => {
    if (step >= 2 && tenantId) void loadVerifications(tenantId);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- load when entering approval step
  }, [step, tenantId]);

  async function createWorkspace(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setPending(true);
    try {
      const res = await api.postHeaders<WorkspaceResponse>(
        "/api/v1/workspaces",
        {
          clinic_name: clinicName,
          slug,
          location_name: locationName,
          timezone,
          practitioner_display_name: practitionerName || null,
          specialty_codes: [specialty],
        },
        { "Idempotency-Key": idemKey },
      );
      setCreated(res);
      setSelectedTenant(res.tenant.id);
      clearWorkspaceContextCache();
      setStep(1);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPending(false);
    }
  }

  async function approvePractitioner(practitionerId: string) {
    if (!tenantId) return;
    setError("");
    setPending(true);
    try {
      await api.post(
        `/api/v1/tenants/${tenantId}/verification`,
        { practitioner_id: practitionerId, status: "approved" },
        tenantId,
      );
      await loadVerifications(tenantId);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPending(false);
    }
  }

  const progressLabel = useMemo(() => `Step ${step + 1} of ${STEPS.length}: ${STEPS[step]}`, [step]);

  if (!me) return <LoadingState label="Loading onboarding" />;

  return (
    <Shell>
      <PageHeader
        title="Clinic setup"
        description="Create your workspace, approve the primary practitioner, then invite your team. Each step saves on the server."
      />
      <p className="hos-helper" role="status">
        {progressLabel}
      </p>
      <ol className="hos-onboarding-steps" aria-label="Setup progress">
        {STEPS.map((label, i) => (
          <li key={label} data-active={i === step ? "true" : "false"} data-done={i < step ? "true" : "false"}>
            {label}
          </li>
        ))}
      </ol>
      {error ? (
        <Alert tone="danger" title="Could not continue">
          {error}
        </Alert>
      ) : null}

      {step === 0 ? (
        <Card title="Create clinic workspace">
          {me.tenants.length > 0 ? (
            <Alert tone="info" title="You already have a workspace">
              Continue to review setup, or create another clinic below.
              <p>
                <Button type="button" size="sm" variant="secondary" onClick={() => setStep(1)}>
                  Review existing setup
                </Button>
              </p>
            </Alert>
          ) : null}
          <form onSubmit={createWorkspace}>
            <Field label="Clinic name" htmlFor="clinic-name" required description="Shown to staff and patients.">
              {() => (
                <Input
                  id="clinic-name"
                  value={clinicName}
                  onChange={(e) => setClinicName(e.target.value)}
                  required
                  minLength={1}
                  maxLength={200}
                />
              )}
            </Field>
            <Field
              label="Workspace URL slug"
              htmlFor="slug"
              required
              description="Lowercase letters, numbers, hyphens. Used in APIs and support."
            >
              {() => (
                <Input
                  id="slug"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  required
                  pattern="[a-z0-9-]+"
                  maxLength={120}
                />
              )}
            </Field>
            <Field label="Primary location name" htmlFor="loc-name" required>
              {() => (
                <Input
                  id="loc-name"
                  value={locationName}
                  onChange={(e) => setLocationName(e.target.value)}
                  required
                />
              )}
            </Field>
            <Field label="Timezone" htmlFor="tz" required description="Service day and queue tokens use this zone.">
              {() => (
                <Input id="tz" value={timezone} onChange={(e) => setTimezone(e.target.value)} required />
              )}
            </Field>
            <Field label="Primary practitioner display name" htmlFor="pract-name">
              {() => (
                <Input
                  id="pract-name"
                  value={practitionerName}
                  onChange={(e) => setPractitionerName(e.target.value)}
                  maxLength={200}
                />
              )}
            </Field>
            <Field label="Specialty" htmlFor="specialty" required>
              {() => (
                <Select
                  id="specialty"
                  value={specialty}
                  onChange={(e) => setSpecialty(e.target.value)}
                  required
                  options={SPECIALTIES}
                />
              )}
            </Field>
            <p className="hos-helper">
              The owner practitioner is created as <strong>pending</strong> until an authorized
              administrator approves them. Appointment booking stays blocked until then.
            </p>
            <p>
              <Button type="submit" loading={pending}>
                Create workspace
              </Button>
            </p>
          </form>
        </Card>
      ) : null}

      {step === 1 ? (
        <Card title="Clinic created">
          {created ? (
            <>
              <p>
                <strong>{created.tenant.name}</strong> ({created.tenant.slug}) ·{" "}
                <Status value={created.tenant.status} />
              </p>
              <p className="hos-helper">
                Location: {created.location.name} · {created.location.timezone}
              </p>
              <p className="hos-helper">
                Practitioner: {created.practitioner.display_name} · Role: {created.membership.role}
              </p>
              <p className="hos-helper">
                Trial: {created.subscription.plan_code} · <Status value={created.subscription.status} />
              </p>
              <p className="hos-helper">
                Specialties: {created.specialties_enabled.join(", ") || "—"}
              </p>
            </>
          ) : (
            <EmptyState title="Using an existing workspace">
              Selected tenant is active. Continue to practitioner approval.
            </EmptyState>
          )}
          <div className="hos-quick-actions">
            <Button type="button" onClick={() => setStep(2)}>
              Continue to practitioner approval
            </Button>
            <Button type="button" variant="secondary" onClick={() => router.push("/admin")}>
              Clinic settings
            </Button>
          </div>
        </Card>
      ) : null}

      {step === 2 ? (
        <Card title="Practitioner verification">
          <p className="hos-helper">
            Pending is not a failure — booking and the schedule picker require{" "}
            <strong>approved</strong> practitioners. Approval requires the{" "}
            <code>staff.manage</code> permission (typically the clinic owner).
          </p>
          {verifyLoading ? <LoadingState label="Loading verification status" /> : null}
          {!verifyLoading && verifications.length === 0 ? (
            <EmptyState title="No verification records">
              Register a practitioner under Clinic settings or create a workspace first.
            </EmptyState>
          ) : null}
          <ul className="hos-onboarding-list">
            {verifications.map((v) => (
              <li key={v.practitioner_id}>
                <strong>{v.display_name}</strong> · <Status value={v.status} />
                {v.reason ? <span className="hos-helper"> — {v.reason}</span> : null}
                {v.status === "pending" ? (
                  <p>
                    <Button
                      type="button"
                      size="sm"
                      loading={pending}
                      onClick={() => void approvePractitioner(v.practitioner_id)}
                    >
                      Approve practitioner
                    </Button>
                  </p>
                ) : null}
                {v.status === "approved" ? (
                  <p className="hos-helper">Ready for appointment booking.</p>
                ) : null}
              </li>
            ))}
          </ul>
          <div className="hos-quick-actions">
            <Button type="button" variant="secondary" onClick={() => setStep(1)}>
              Back
            </Button>
            <Button type="button" onClick={() => setStep(3)}>
              Continue
            </Button>
          </div>
        </Card>
      ) : null}

      {step === 3 ? (
        <Card title="Invite staff">
          <p>
            Invite receptionists, nurses, doctors, and other roles from Staff or Team. After you
            create an invitation, share it once with WhatsApp (click-to-chat) or Copy link. Messages
            are never sent automatically. Invitations expire; email delivery uses the server
            notification adapter when configured.
          </p>
          <div className="hos-quick-actions">
            <Button type="button" onClick={() => router.push("/staff")}>
              Open staff invitations
            </Button>
            <Button type="button" variant="secondary" onClick={() => router.push("/team")}>
              Open team
            </Button>
            <Button type="button" variant="secondary" onClick={() => setStep(4)}>
              Skip for now
            </Button>
          </div>
          <p>
            <Button type="button" onClick={() => setStep(4)}>
              Continue to dashboard
            </Button>
          </p>
        </Card>
      ) : null}

      {step === 4 ? (
        <Card title="You’re ready">
          <p>Open the clinic dashboard to register patients, book appointments, and run reception.</p>
          <div className="hos-quick-actions">
            <Button type="button" onClick={() => router.push("/")}>
              Go to dashboard
            </Button>
            <Link href="/patients">Patients</Link>
            <Link href="/schedule">Appointments</Link>
          </div>
        </Card>
      ) : null}
    </Shell>
  );
}
