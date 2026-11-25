import { FormEvent, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  LoadingState,
  MoneyDisplay,
  PatientIdentityHeader,
  Select,
  Status,
  Table,
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
  Td,
  Th,
} from "@healthcare-os/ui";
import { apiFetch } from "../../lib/api";
import { fmtWhen, statusLabel } from "../../lib/format";
import { hasPerm } from "../../lib/nav";
import {
  getPatient,
  getPatientOverview,
  getPatientTimeline,
  Patient,
  PatientOverview,
  TimelineItem,
  updatePatient,
} from "../../lib/patientsApi";
import {
  listEstimates,
  listInvoiceCreditNotes,
  listPaymentRefunds,
  type CreditNote,
  type Estimate,
  type Refund,
} from "../../lib/billingApi";
import { listAppointments, Appointment } from "../../lib/schedulingApi";
import { useSession } from "../../lib/session";

type SoftList<T> = { items?: T[]; ok: boolean; forbidden: boolean };

async function softGet<T>(
  tenantId: string,
  path: string,
): Promise<SoftList<T>> {
  const res = await apiFetch(`/api/v1/tenants/${tenantId}${path}`, {
    tenantId,
  });
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) return { ok: false, forbidden: true };
  if (res.status !== 200 || !res.json) return { ok: false, forbidden: false };
  const data = res.json;
  if (Array.isArray(data)) return { items: data as T[], ok: true, forbidden: false };
  if (data && typeof data === "object" && "items" in data) {
    return {
      items: (data as { items: T[] }).items,
      ok: true,
      forbidden: false,
    };
  }
  return { items: [data as T], ok: true, forbidden: false };
}

const TIMELINE_CATEGORIES = [
  { value: "", label: "All" },
  { value: "scheduling", label: "Scheduling" },
  { value: "clinical", label: "Clinical" },
  { value: "billing", label: "Billing" },
  { value: "documents", label: "Documents" },
  { value: "admin", label: "Admin" },
  { value: "care", label: "Care" },
] as const;

export function PatientProfile({
  patientId,
  onBack,
  onBook,
  onConsult,
  onOpenBilling,
  onOpenTreatmentPlans,
  onSessionExpired,
}: {
  patientId: string;
  onBack: () => void;
  onBook: (patientId: string) => void;
  onConsult?: (patientId: string) => void;
  onOpenBilling?: (
    patientId: string,
    tab?: "estimates" | "invoices" | "payments" | "dues" | "refunds" | "credits",
  ) => void;
  onOpenTreatmentPlans?: (patientId: string) => void;
  onSessionExpired: () => void;
}) {
  const { tenant, workspace } = useSession();
  const canUpdate = hasPerm(workspace?.permissions, "patient.update");
  const canDentalRead = hasPerm(workspace?.permissions, "dental.read");

  const [patient, setPatient] = useState<Patient | null>(null);
  const [overview, setOverview] = useState<PatientOverview | null>(null);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [encounters, setEncounters] = useState<Array<Record<string, unknown>>>([]);
  const [plans, setPlans] = useState<Array<Record<string, unknown>>>([]);
  const [invoices, setInvoices] = useState<Array<Record<string, unknown>>>([]);
  const [payments, setPayments] = useState<Array<Record<string, unknown>>>([]);
  const [profileRefunds, setProfileRefunds] = useState<
    Array<{ paymentId: string; refund: Refund }>
  >([]);
  const [profileCreditNotes, setProfileCreditNotes] = useState<
    Array<{ invoiceId: string; note: CreditNote }>
  >([]);
  const [estimates, setEstimates] = useState<Estimate[]>([]);
  const [followUps, setFollowUps] = useState<Array<Record<string, unknown>>>([]);
  const [consents, setConsents] = useState<Array<Record<string, unknown>>>([]);
  const [omitted, setOmitted] = useState<string[]>([]);
  const canBilling = hasPerm(workspace?.permissions, "billing.read");

  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [timelineCursor, setTimelineCursor] = useState<string | null>(null);
  const [timelineCategory, setTimelineCategory] = useState("");
  const [timelineLoading, setTimelineLoading] = useState(false);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState<string | null>(null);
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);

  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [dob, setDob] = useState("");
  const [emergName, setEmergName] = useState("");
  const [emergPhone, setEmergPhone] = useState("");

  async function loadCore() {
    if (!tenant) return;
    setLoading(true);
    setError(null);
    setOmitted([]);
    try {
      const [p, ov] = await Promise.all([
        getPatient(tenant.id, patientId),
        getPatientOverview(tenant.id, patientId),
      ]);
      setPatient(p);
      setOverview(ov);
      setName(p.display_name);
      setPhone(p.phone ?? "");
      setEmail(p.email ?? "");
      setDob(p.date_of_birth ?? "");
      setEmergName(p.emergency_contact_name ?? "");
      setEmergPhone(p.emergency_contact_phone ?? "");

      const skipped: string[] = [];
      try {
        const appts = await listAppointments(tenant.id, {
          patientId,
          limit: 50,
        });
        setAppointments(appts);
      } catch {
        skipped.push("appointments");
      }

      const enc = await softGet<Record<string, unknown>>(
        tenant.id,
        `/encounters?patient_id=${patientId}&limit=50`,
      );
      if (enc.forbidden) skipped.push("encounters");
      else if (enc.ok) setEncounters(enc.items ?? []);

      const pl = await softGet<Record<string, unknown>>(
        tenant.id,
        `/treatment-plans?patient_id=${patientId}`,
      );
      if (pl.forbidden) skipped.push("treatment_plans");
      else if (pl.ok) setPlans(pl.items ?? []);

      const inv = await softGet<Record<string, unknown>>(
        tenant.id,
        `/invoices?patient_id=${patientId}&limit=50`,
      );
      if (inv.forbidden) skipped.push("invoices");
      else if (inv.ok) setInvoices(inv.items ?? []);

      const pay = await softGet<Record<string, unknown>>(
        tenant.id,
        `/payments?patient_id=${patientId}&limit=50`,
      );
      if (pay.forbidden) skipped.push("payments");
      else if (pay.ok) setPayments(pay.items ?? []);

      setProfileRefunds([]);
      setProfileCreditNotes([]);

      if (canBilling) {
        try {
          const est = await listEstimates(tenant.id, {
            patientId,
            limit: 50,
          });
          setEstimates(est);
        } catch {
          skipped.push("estimates");
          setEstimates([]);
        }

        if (pay.ok && (pay.items?.length ?? 0) > 0) {
          const paymentIds = pay.items!.map((row) => String(row.id ?? ""));
          const refundBatches = await Promise.all(
            paymentIds.map(async (pid) => {
              if (!pid) return [] as Array<{ paymentId: string; refund: Refund }>;
              try {
                const items = await listPaymentRefunds(tenant.id, pid);
                return items.map((refund) => ({ paymentId: pid, refund }));
              } catch {
                return [] as Array<{ paymentId: string; refund: Refund }>;
              }
            }),
          );
          setProfileRefunds(refundBatches.flat());
        }

        if (inv.ok && (inv.items?.length ?? 0) > 0) {
          const invoiceIds = inv.items!.map((row) => String(row.id ?? ""));
          const cnBatches = await Promise.all(
            invoiceIds.map(async (iid) => {
              if (!iid) return [] as Array<{ invoiceId: string; note: CreditNote }>;
              try {
                const items = await listInvoiceCreditNotes(tenant.id, iid);
                return items.map((note) => ({ invoiceId: iid, note }));
              } catch {
                return [] as Array<{ invoiceId: string; note: CreditNote }>;
              }
            }),
          );
          setProfileCreditNotes(cnBatches.flat());
        }
      } else {
        setEstimates([]);
      }

      const fus = await softGet<Record<string, unknown>>(
        tenant.id,
        `/follow-ups?patient_id=${patientId}&limit=50`,
      );
      if (fus.forbidden) skipped.push("follow_ups");
      else if (fus.ok) setFollowUps(fus.items ?? []);

      const cons = await softGet<Record<string, unknown>>(
        tenant.id,
        `/patients/${patientId}/communication-consents`,
      );
      if (cons.forbidden) skipped.push("consents");
      else if (cons.ok) setConsents(cons.items ?? []);

      setOmitted(skipped);
    } catch (e) {
      if (String(e).includes("session_expired")) onSessionExpired();
      else if (String(e).includes("forbidden"))
        setError("You do not have permission to view this patient.");
      else if (String(e).includes("not_found")) setError("Patient not found.");
      else setError("Failed to load patient profile.");
    } finally {
      setLoading(false);
    }
  }

  async function loadTimeline(reset: boolean, cursor?: string | null) {
    if (!tenant) return;
    setTimelineLoading(true);
    try {
      const page = await getPatientTimeline(tenant.id, patientId, {
        category: timelineCategory || undefined,
        cursor: cursor || undefined,
        limit: 40,
      });
      setTimeline((prev) => (reset ? page.items : [...prev, ...page.items]));
      setTimelineCursor(page.next_cursor);
    } catch (e) {
      if (String(e).includes("session_expired")) onSessionExpired();
      else setError("Failed to load timeline.");
    } finally {
      setTimelineLoading(false);
    }
  }

  useEffect(() => {
    void loadCore();
    // Clear patient-scoped lists when id/tenant changes
    setTimeline([]);
    setTimelineCursor(null);
  }, [tenant?.id, patientId]);

  useEffect(() => {
    void loadTimeline(true);
  }, [tenant?.id, patientId, timelineCategory]);

  async function onSave(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !canUpdate) return;
    setSaving(true);
    setSavedMsg(null);
    try {
      const updated = await updatePatient(tenant.id, patientId, {
        display_name: name.trim(),
        phone: phone.trim() || null,
        email: email.trim() || null,
        date_of_birth: dob || null,
        emergency_contact_name: emergName.trim() || null,
        emergency_contact_phone: emergPhone.trim() || null,
      });
      setPatient(updated);
      if (updated.potential_duplicates?.length) {
        setSavedMsg(
          `Saved. Possible duplicates: ${updated.potential_duplicates.length}.`,
        );
      } else {
        setSavedMsg("Patient details saved.");
      }
      setError(null);
    } catch (err) {
      if (String(err).includes("session_expired")) onSessionExpired();
      else setError("Save failed.");
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive() {
    if (!tenant || !patient || !canUpdate) return;
    try {
      const updated = await updatePatient(tenant.id, patientId, {
        is_active: !patient.is_active,
      });
      setPatient(updated);
      setConfirmDeactivate(false);
    } catch (err) {
      if (String(err).includes("session_expired")) onSessionExpired();
      else setError("Could not update status.");
    }
  }

  if (loading) return <LoadingState label="Loading patient chart" />;
  if (error && !patient) {
    return (
      <Alert tone="danger" title="Patient">
        {error}
        <div style={{ marginTop: 12 }}>
          <Button type="button" variant="secondary" onClick={onBack}>
            Back to directory
          </Button>
        </div>
      </Alert>
    );
  }
  if (!patient) {
    return (
      <EmptyState title="Patient unavailable">
        <Button type="button" onClick={onBack}>
          Back
        </Button>
      </EmptyState>
    );
  }

  return (
    <div className="hos-patient-profile">
      <div className="hos-toolbar-row">
        <Button type="button" variant="secondary" size="sm" onClick={onBack}>
          ← Patients
        </Button>
        <Button type="button" size="sm" onClick={() => onBook(patient.id)}>
          Book appointment
        </Button>
        {onConsult && (
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => onConsult(patient.id)}
          >
            Open consultation
          </Button>
        )}
        {canUpdate && (
          <Button
            type="button"
            size="sm"
            variant="secondary"
            onClick={() => setConfirmDeactivate(true)}
          >
            {patient.is_active ? "Deactivate" : "Reactivate"}
          </Button>
        )}
      </div>

      <PatientIdentityHeader
        name={patient.display_name}
        patientId={patient.id}
        meta={[patient.phone, patient.email].filter(Boolean).join(" · ") || "No contact"}
        status={patient.is_active ? "current" : "revoked"}
      />

      {error && (
        <Alert tone="danger" title="Notice">
          {error}
        </Alert>
      )}
      {savedMsg && (
        <Alert tone="success" title="Saved">
          {savedMsg}
        </Alert>
      )}
      {omitted.length > 0 && (
        <p className="hos-caption">
          Sections omitted (forbidden or unavailable): {omitted.join(", ")}
        </p>
      )}

      {overview && (
        <div className="hos-dash-grid">
          <Card title="Last visit">
            <p>{fmtWhen(overview.last_visit_at)}</p>
          </Card>
          <Card title="Next appointment">
            <p>{fmtWhen(overview.next_appointment_at)}</p>
          </Card>
          <Card title="Outstanding">
            <MoneyDisplay
              amount={overview.outstanding_balance}
              currency={overview.currency}
            />
          </Card>
          <Card title="Follow-ups">
            <p>
              Open {overview.open_followups} · Overdue {overview.overdue_followups}
            </p>
          </Card>
        </div>
      )}

      <Tabs defaultValue="demographics">
        <TabsList>
          <TabsTrigger value="demographics">Demographics</TabsTrigger>
          <TabsTrigger value="history">History</TabsTrigger>
          <TabsTrigger value="appointments">Appointments</TabsTrigger>
          <TabsTrigger value="clinical">Clinical</TabsTrigger>
          <TabsTrigger value="billing">Billing</TabsTrigger>
          <TabsTrigger value="care">Care & consent</TabsTrigger>
        </TabsList>

        <TabsContent value="demographics">
          <Card title="Demographics">
            {canUpdate ? (
              <form onSubmit={onSave}>
                <Field label="Display name" htmlFor="edit-name" required>
                  {({ describedBy }) => (
                    <Input
                      id="edit-name"
                      aria-describedby={describedBy}
                      value={name}
                      onChange={(ev) => setName(ev.target.value)}
                      required
                    />
                  )}
                </Field>
                <Field label="Phone" htmlFor="edit-phone">
                  {({ describedBy }) => (
                    <Input
                      id="edit-phone"
                      aria-describedby={describedBy}
                      value={phone}
                      onChange={(ev) => setPhone(ev.target.value)}
                    />
                  )}
                </Field>
                <Field label="Email" htmlFor="edit-email">
                  {({ describedBy }) => (
                    <Input
                      id="edit-email"
                      type="email"
                      aria-describedby={describedBy}
                      value={email}
                      onChange={(ev) => setEmail(ev.target.value)}
                    />
                  )}
                </Field>
                <Field label="Date of birth" htmlFor="edit-dob">
                  {({ describedBy }) => (
                    <Input
                      id="edit-dob"
                      type="date"
                      aria-describedby={describedBy}
                      value={dob}
                      onChange={(ev) => setDob(ev.target.value)}
                    />
                  )}
                </Field>
                <Field label="Emergency contact" htmlFor="edit-emerg-name">
                  {({ describedBy }) => (
                    <Input
                      id="edit-emerg-name"
                      aria-describedby={describedBy}
                      value={emergName}
                      onChange={(ev) => setEmergName(ev.target.value)}
                    />
                  )}
                </Field>
                <Field label="Emergency phone" htmlFor="edit-emerg-phone">
                  {({ describedBy }) => (
                    <Input
                      id="edit-emerg-phone"
                      aria-describedby={describedBy}
                      value={emergPhone}
                      onChange={(ev) => setEmergPhone(ev.target.value)}
                    />
                  )}
                </Field>
                <Button type="submit" disabled={saving} loading={saving}>
                  Save changes
                </Button>
              </form>
            ) : (
              <dl className="hos-dl">
                <div>
                  <dt>Phone</dt>
                  <dd>{patient.phone ?? "—"}</dd>
                </div>
                <div>
                  <dt>Email</dt>
                  <dd>{patient.email ?? "—"}</dd>
                </div>
                <div>
                  <dt>Date of birth</dt>
                  <dd>{patient.date_of_birth ?? "—"}</dd>
                </div>
              </dl>
            )}
          </Card>
        </TabsContent>

        <TabsContent value="history">
          <Card title="Chronological history">
            <Field label="Category" htmlFor="tl-cat">
              {({ describedBy }) => (
                <Select
                  id="tl-cat"
                  aria-describedby={describedBy}
                  value={timelineCategory}
                  onChange={(ev) => setTimelineCategory(ev.target.value)}
                  options={[...TIMELINE_CATEGORIES]}
                />
              )}
            </Field>
            {timelineLoading && timeline.length === 0 ? (
              <LoadingState label="Loading timeline" />
            ) : timeline.length === 0 ? (
              <EmptyState title="No timeline events">
                Events appear as visits, clinical notes, billing, and follow-ups occur.
              </EmptyState>
            ) : (
              <ol className="hos-timeline">
                {timeline.map((ev) => (
                  <li key={ev.event_id} className="hos-timeline-item">
                    <div className="hos-timeline-meta">
                      <time dateTime={ev.occurred_at}>{fmtWhen(ev.occurred_at)}</time>
                      <span className="hos-badge-soft">{ev.category}</span>
                      {ev.status && <Status value={ev.status} />}
                    </div>
                    <strong>{ev.title}</strong>
                    {ev.summary && <p className="hos-muted">{ev.summary}</p>}
                    <p className="hos-caption">
                      {ev.kind}
                      {ev.resource_type ? ` · ${ev.resource_type}` : ""}
                    </p>
                  </li>
                ))}
              </ol>
            )}
            {timelineCursor && (
              <Button
                type="button"
                variant="secondary"
                disabled={timelineLoading}
                onClick={() => void loadTimeline(false, timelineCursor)}
              >
                Load more
              </Button>
            )}
          </Card>
        </TabsContent>

        <TabsContent value="appointments">
          <Card title="Appointments">
            {appointments.length === 0 ? (
              <EmptyState title="No appointments">None on file for this patient.</EmptyState>
            ) : (
              <Table
                columns={
                  <>
                    <Th>When</Th>
                    <Th>Status</Th>
                    <Th>Queue</Th>
                  </>
                }
              >
                {appointments.map((a) => (
                  <tr key={a.id}>
                    <Td>{fmtWhen(a.start_at)}</Td>
                    <Td>{statusLabel(a.status)}</Td>
                    <Td>{a.queue_token ?? "—"}</Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </TabsContent>

        <TabsContent value="clinical">
          <Card title="Encounters">
            {encounters.length === 0 ? (
              <EmptyState title="No encounters">No authorized encounters returned.</EmptyState>
            ) : (
              <Table
                columns={
                  <>
                    <Th>Opened</Th>
                    <Th>Status</Th>
                  </>
                }
              >
                {encounters.map((e) => (
                  <tr key={String(e.id)}>
                    <Td>{fmtWhen(String(e.opened_at ?? ""))}</Td>
                    <Td>{String(e.status ?? "—")}</Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
          <Card title="Treatment plans">
            {canDentalRead && onOpenTreatmentPlans && (
              <div className="hos-toolbar-row">
                <Button
                  type="button"
                  size="sm"
                  onClick={() => onOpenTreatmentPlans(patient.id)}
                >
                  Open treatment plans
                </Button>
              </div>
            )}
            {plans.length === 0 ? (
              <EmptyState title="No plans">No authorized plans returned.</EmptyState>
            ) : (
              <Table
                columns={
                  <>
                    <Th>Status</Th>
                    <Th>Version</Th>
                    <Th>Items</Th>
                  </>
                }
              >
                {plans.map((p) => (
                  <tr key={String(p.id)}>
                    <Td>{String(p.status ?? "—")}</Td>
                    <Td>{String(p.version ?? "—")}</Td>
                    <Td>
                      {Array.isArray((p as { items?: unknown[] }).items)
                        ? (p as { items: unknown[] }).items.length
                        : "—"}
                    </Td>
                  </tr>
                ))}
              </Table>
            )}
            {canDentalRead && (
              <p className="hos-caption">
                The odontogram chart is encounter-scoped — open an encounter Dental tab to chart
                teeth for the current visit.
              </p>
            )}
          </Card>
          <p className="hos-caption">
            Clinical note, diagnosis, and prescription editors are out of scope for M5;
            events still appear in History when the timeline API returns them.
          </p>
        </TabsContent>

        <TabsContent value="billing">
          {onOpenBilling && canBilling && (
            <div className="hos-toolbar-row">
              <Button
                type="button"
                size="sm"
                onClick={() => onOpenBilling(patient.id, "invoices")}
              >
                Open billing workspace
              </Button>
              <Button
                type="button"
                size="sm"
                variant="secondary"
                onClick={() => onOpenBilling(patient.id, "dues")}
              >
                Outstanding dues
              </Button>
            </div>
          )}
          <Card title="Estimates">
            {estimates.length === 0 ? (
              <EmptyState title="No estimates">No authorized estimates returned.</EmptyState>
            ) : (
              <Table
                columns={
                  <>
                    <Th>Status</Th>
                    <Th>Total</Th>
                    <Th>Valid until</Th>
                  </>
                }
              >
                {estimates.map((est) => (
                  <tr key={est.id}>
                    <Td>{est.status}</Td>
                    <Td>
                      <MoneyDisplay amount={est.grand_total} currency={est.currency} />
                    </Td>
                    <Td>{est.valid_until ?? "—"}</Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
          <Card title="Invoices">
            {invoices.length === 0 ? (
              <EmptyState title="No invoices">No authorized invoices returned.</EmptyState>
            ) : (
              <Table
                columns={
                  <>
                    <Th>Status</Th>
                    <Th>Total</Th>
                    <Th>Allocated</Th>
                    <Th>Outstanding</Th>
                  </>
                }
              >
                {invoices.map((inv) => (
                  <tr key={String(inv.id)}>
                    <Td>{String(inv.status ?? "—")}</Td>
                    <Td>
                      <MoneyDisplay
                        amount={String(inv.grand_total ?? "0")}
                        currency={String(inv.currency ?? "INR")}
                      />
                    </Td>
                    <Td>
                      <MoneyDisplay
                        amount={String(inv.allocated_amount ?? "0")}
                        currency={String(inv.currency ?? "INR")}
                      />
                    </Td>
                    <Td>
                      <MoneyDisplay
                        amount={String(inv.outstanding_amount ?? "0")}
                        currency={String(inv.currency ?? "INR")}
                      />
                    </Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
          <Card title="Payments">
            {payments.length === 0 ? (
              <EmptyState title="No payments">No authorized payments returned.</EmptyState>
            ) : (
              <Table
                columns={
                  <>
                    <Th>Method</Th>
                    <Th>Amount</Th>
                    <Th>Unallocated</Th>
                    <Th>Status</Th>
                  </>
                }
              >
                {payments.map((pay) => (
                  <tr key={String(pay.id)}>
                    <Td>{String(pay.method ?? "—")}</Td>
                    <Td>
                      <MoneyDisplay
                        amount={String(pay.amount ?? "0")}
                        currency={String(pay.currency ?? "INR")}
                      />
                    </Td>
                    <Td>
                      <MoneyDisplay
                        amount={String(pay.unallocated_amount ?? "0")}
                        currency={String(pay.currency ?? "INR")}
                      />
                    </Td>
                    <Td>{String(pay.status ?? "—")}</Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
          {canBilling && (
            <>
              <Card title="Refunds">
                {profileRefunds.length === 0 ? (
                  <EmptyState title="No refunds">No refunds returned for patient payments.</EmptyState>
                ) : (
                  <Table
                    columns={
                      <>
                        <Th>Payment</Th>
                        <Th>Amount</Th>
                        <Th>Status</Th>
                        <Th>Reason</Th>
                      </>
                    }
                  >
                    {profileRefunds.map(({ paymentId, refund }) => (
                      <tr key={refund.id}>
                        <Td>{paymentId.slice(0, 8)}</Td>
                        <Td>
                          <MoneyDisplay amount={refund.amount} currency={refund.currency} />
                        </Td>
                        <Td>{refund.status}</Td>
                        <Td>
                          {refund.reason.length > 48
                            ? `${refund.reason.slice(0, 48)}…`
                            : refund.reason}
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
              <Card title="Credit notes">
                {profileCreditNotes.length === 0 ? (
                  <EmptyState title="No credit notes">
                    No credit notes returned for patient invoices.
                  </EmptyState>
                ) : (
                  <Table
                    columns={
                      <>
                        <Th>Invoice</Th>
                        <Th>Status</Th>
                        <Th>Amount</Th>
                        <Th>Doc #</Th>
                      </>
                    }
                  >
                    {profileCreditNotes.map(({ invoiceId, note }) => (
                      <tr key={note.id}>
                        <Td>{invoiceId.slice(0, 8)}</Td>
                        <Td>{note.status}</Td>
                        <Td>
                          <MoneyDisplay amount={note.amount} currency={note.currency} />
                        </Td>
                        <Td>
                          {note.doc_number != null
                            ? note.financial_year
                              ? `${note.doc_number} / FY ${note.financial_year}`
                              : String(note.doc_number)
                            : "—"}
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
              {onOpenBilling && (
                <div className="hos-toolbar-row">
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={() => onOpenBilling(patient.id, "refunds")}
                  >
                    Open refunds
                  </Button>
                  <Button
                    type="button"
                    size="sm"
                    variant="secondary"
                    onClick={() => onOpenBilling(patient.id, "credits")}
                  >
                    Open credit notes
                  </Button>
                </div>
              )}
            </>
          )}
          <p className="hos-caption">
            Refunds return money against a payment (clinic record, not bank settlement). Credit notes
            correct invoice outstanding and are not cash refunds. Totals are backend-authoritative.
          </p>
        </TabsContent>

        <TabsContent value="care">
          <Card title="Follow-ups">
            {followUps.length === 0 ? (
              <EmptyState title="No follow-ups">None returned.</EmptyState>
            ) : (
              <Table
                columns={
                  <>
                    <Th>Due</Th>
                    <Th>Reason</Th>
                    <Th>Status</Th>
                  </>
                }
              >
                {followUps.map((f) => (
                  <tr key={String(f.id)}>
                    <Td>{fmtWhen(String(f.due_at ?? ""))}</Td>
                    <Td>{String(f.reason ?? "—")}</Td>
                    <Td>{String(f.status ?? "—")}</Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
          <Card title="Communication consent">
            {consents.length === 0 ? (
              <EmptyState title="No consents">None on file or not authorized.</EmptyState>
            ) : (
              <Table
                columns={
                  <>
                    <Th>Channel</Th>
                    <Th>Purpose</Th>
                    <Th>Status</Th>
                  </>
                }
              >
                {consents.map((c) => (
                  <tr key={String(c.id)}>
                    <Td>{String(c.channel ?? "—")}</Td>
                    <Td>{String(c.purpose ?? "—")}</Td>
                    <Td>{String(c.status ?? "—")}</Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        open={confirmDeactivate}
        onOpenChange={setConfirmDeactivate}
        title={patient.is_active ? "Deactivate patient?" : "Reactivate patient?"}
        confirmLabel={patient.is_active ? "Deactivate" : "Reactivate"}
        onConfirm={() => void toggleActive()}
      >
        {patient.is_active
          ? "Inactive patients are hidden from the default directory."
          : "Restore this patient to the active directory."}
      </ConfirmDialog>
    </div>
  );
}
