"use client";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Breadcrumbs,
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
  WhatsAppShareAction,
} from "@healthcare-os/ui";
import { api, type Me } from "@/lib/api";
import {
  appOrigin,
  portalActivationShareUrl,
  portalEnrollMessage,
  portalHomeShareUrl,
} from "@/lib/shareLinks";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../../shell";

type Patient = {
  id: string;
  display_name: string;
  phone: string | null;
  email: string | null;
  date_of_birth: string | null;
  emergency_contact_name: string | null;
  emergency_contact_phone: string | null;
  is_active: boolean;
};
type Appointment = {
  id: string;
  start_at: string;
  status: string;
  practitioner_id: string;
  queue_token?: number | null;
};
type Encounter = { id: string; status: string; opened_at: string };
type Plan = { id: string; status: string; version: number };
type Recall = { id: string; status: string; due_date: string; reason: string };
type Invoice = {
  id: string;
  status: string;
  grand_total: string;
  outstanding_amount: string;
  currency: string;
};
type Payment = { id: string; status: string; method: string; amount: string; currency: string };
type Overview = {
  last_visit_at: string | null;
  next_appointment_at: string | null;
  next_appointment_id: string | null;
  outstanding_balance: string;
  currency: string;
  follow_up_due: string | null;
  open_followups?: number;
  overdue_followups?: number;
  completed_followups?: number;
};
type CareFollowUp = {
  id: string;
  due_at: string;
  reason: string;
  status: string;
  priority: string;
  category: string;
};
type CommLog = {
  id: string;
  channel: string;
  purpose: string;
  outcome: string;
  occurred_at: string;
  note: string | null;
};
type CommConsent = {
  id: string;
  channel: string;
  purpose: string;
  status: string;
  captured_at: string;
};
type TimelineItem = {
  event_id: string;
  kind: string;
  category: string;
  occurred_at: string;
  title: string;
  summary: string | null;
  resource_type: string;
  resource_id: string;
  status: string | null;
  href: string | null;
};
type TimelinePage = { items: TimelineItem[]; next_cursor: string | null };

const TIMELINE_CATEGORIES = [
  { value: "", label: "All" },
  { value: "scheduling", label: "Scheduling" },
  { value: "clinical", label: "Clinical" },
  { value: "billing", label: "Billing" },
  { value: "documents", label: "Documents" },
  { value: "admin", label: "Admin" },
  { value: "care", label: "Care" },
] as const;

function fmtWhen(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export default function PatientWorkspacePage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const id = params.id;
  const [patient, setPatient] = useState<Patient | null>(null);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [encounters, setEncounters] = useState<Encounter[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [recalls, setRecalls] = useState<Recall[]>([]);
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [payments, setPayments] = useState<Payment[]>([]);
  const [credit, setCredit] = useState<string | null>(null);
  const [overview, setOverview] = useState<Overview | null>(null);
  const [followUps, setFollowUps] = useState<CareFollowUp[]>([]);
  const [commLogs, setCommLogs] = useState<CommLog[]>([]);
  const [consents, setConsents] = useState<CommConsent[]>([]);
  const [waPurpose, setWaPurpose] = useState("care_followup");
  const [clinicName, setClinicName] = useState("your clinic");
  const [timeline, setTimeline] = useState<TimelineItem[]>([]);
  const [timelineCursor, setTimelineCursor] = useState<string | null>(null);
  const [timelineCategory, setTimelineCategory] = useState("");
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState("");
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");
  const [dob, setDob] = useState("");
  const [emergName, setEmergName] = useState("");
  const [emergPhone, setEmergPhone] = useState("");
  const [portalEmail, setPortalEmail] = useState("");
  const [portalBusy, setPortalBusy] = useState(false);
  const [portalMsg, setPortalMsg] = useState("");
  const [portalShare, setPortalShare] = useState<{
    email: string;
    message: string;
    resetUrl: string;
    phone: string;
  } | null>(null);

  function loadTimeline(reset: boolean, cursor?: string | null) {
    const t = getSelectedTenant();
    if (!t) return;
    setTimelineLoading(true);
    const cat = timelineCategory ? `&category=${timelineCategory}` : "";
    const cur = cursor ? `&cursor=${encodeURIComponent(cursor)}` : "";
    api
      .get<TimelinePage>(
        `/api/v1/tenants/${t}/patients/${id}/timeline?limit=30${cat}${cur}`,
        t,
      )
      .then((page) => {
        setTimeline((prev) => (reset ? page.items : [...prev, ...page.items]));
        setTimelineCursor(page.next_cursor);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setTimelineLoading(false));
  }

  function load() {
    const t = getSelectedTenant();
    if (!t) {
      router.push("/");
      return;
    }
    setLoading(true);
    const get = <T,>(path: string) => api.get<T>(`/api/v1/tenants/${t}${path}`, t);
    Promise.all([
      get<Patient>(`/patients/${id}`),
      get<{ items: Appointment[] }>(`/appointments?patient_id=${id}&limit=50`),
      get<{ items: Encounter[] }>(`/encounters?patient_id=${id}&limit=50`),
      get<Plan[]>(`/treatment-plans?patient_id=${id}`),
      get<Recall[]>(`/recalls?patient_id=${id}`),
      get<{ items: Invoice[] }>(`/invoices?patient_id=${id}&limit=50`),
      get<{ items: Payment[] }>(`/payments?patient_id=${id}&limit=50`),
      get<{ credit_amount: string }>(`/patients/${id}/credit-balance`),
      get<Overview>(`/patients/${id}/overview`),
      get<CareFollowUp[]>(`/follow-ups?patient_id=${id}&limit=50`).catch(() => []),
      get<CommLog[]>(`/communication-logs?patient_id=${id}&limit=50`).catch(() => []),
      get<CommConsent[]>(`/patients/${id}/communication-consents`).catch(() => []),
    ])
      .then(([p, appts, enc, pl, rec, inv, pay, cred, ov, fus, logs, cons]) => {
        setPatient(p);
        setName(p.display_name);
        setPhone(p.phone ?? "");
        setEmail(p.email ?? "");
        setDob(p.date_of_birth ?? "");
        setEmergName(p.emergency_contact_name ?? "");
        setEmergPhone(p.emergency_contact_phone ?? "");
        setAppointments(appts.items);
        setEncounters(enc.items);
        setPlans(pl);
        setRecalls(rec);
        setInvoices(inv.items);
        setPayments(pay.items);
        setCredit(cred.credit_amount);
        setOverview(ov);
        setFollowUps(fus);
        setCommLogs(logs);
        setConsents(cons);
        setError("");
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [id, router]);
  useEffect(() => {
    const t = getSelectedTenant();
    if (!t) return;
    api
      .get<Me>("/api/v1/auth/me")
      .then((me) => {
        const match = me.tenants.find((x) => x.id === t);
        if (match?.name) setClinicName(match.name);
      })
      .catch(() => undefined);
  }, []);
  useEffect(() => {
    loadTimeline(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload on category/patient only
  }, [id, timelineCategory]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    const t = getSelectedTenant();
    if (!t) return;
    setSaving(true);
    setSavedMsg("");
    try {
      const updated = await api.patch<Patient>(
        `/api/v1/tenants/${t}/patients/${id}`,
        {
          display_name: name,
          phone: phone || null,
          email: email || null,
          date_of_birth: dob || null,
          emergency_contact_name: emergName || null,
          emergency_contact_phone: emergPhone || null,
        },
        t,
      );
      setPatient(updated);
      setError("");
      setSavedMsg("Patient details saved.");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive() {
    const t = getSelectedTenant();
    if (!t || !patient) return;
    try {
      const updated = await api.patch<Patient>(
        `/api/v1/tenants/${t}/patients/${id}`,
        { is_active: !patient.is_active },
        t,
      );
      setPatient(updated);
      setConfirmDeactivate(false);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Shell>
      {loading ? (
        <LoadingState label="Loading patient chart" />
      ) : error && !patient ? (
        <Alert tone="danger" title="Could not load patient">
          {error}
        </Alert>
      ) : patient ? (
        <>
          <Breadcrumbs
            items={[
              { label: "Patients", href: "/patients" },
              { label: "Patient chart" },
            ]}
          />
          <PatientIdentityHeader
            name={patient.display_name}
            patientId={patient.id}
            meta={[patient.phone, patient.email].filter(Boolean).join(" · ") || "No contact on file"}
            status={patient.is_active ? "current" : "revoked"}
          />
          <div className="hos-quick-actions" aria-label="Patient actions">
            <Button
              type="button"
              size="sm"
              onClick={() => router.push(`/schedule?patient=${encodeURIComponent(patient.id)}`)}
            >
              Book appointment
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => router.push("/reception")}
            >
              Reception
            </Button>
            <Button
              type="button"
              size="sm"
              variant="secondary"
              onClick={() => router.push("/follow-ups")}
            >
              Follow-ups
            </Button>
            {patient.is_active ? (
              <Button
                type="button"
                size="sm"
                variant="ghost"
                onClick={() => setConfirmDeactivate(true)}
              >
                Deactivate
              </Button>
            ) : (
              <Button type="button" size="sm" variant="secondary" onClick={() => void toggleActive()}>
                Reactivate
              </Button>
            )}
          </div>
          {error ? (
            <Alert tone="danger" title="Something went wrong">
              {error}
            </Alert>
          ) : null}
          {savedMsg ? (
            <Alert tone="success" title="Saved">
              {savedMsg}
            </Alert>
          ) : null}

          <ConfirmDialog
            open={confirmDeactivate}
            onOpenChange={setConfirmDeactivate}
            title="Deactivate patient?"
            confirmLabel="Deactivate"
            onConfirm={() => void toggleActive()}
          >
            <p>
              {patient.display_name} will be marked inactive. Existing records remain; they will not
              appear in the default active directory.
            </p>
          </ConfirmDialog>

          <Tabs defaultValue="overview">
            <TabsList>
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="timeline">Timeline</TabsTrigger>
              <TabsTrigger value="clinical">Clinical</TabsTrigger>
              <TabsTrigger value="care">Care</TabsTrigger>
              <TabsTrigger value="billing">Billing</TabsTrigger>
              <TabsTrigger value="details">Details</TabsTrigger>
            </TabsList>

            <TabsContent value="overview">
              {overview ? (
                <div className="hos-overview-grid">
                  <Card title="Next appointment">
                    {overview.next_appointment_at ? (
                      <>
                        <p>
                          <strong>{fmtWhen(overview.next_appointment_at)}</strong>
                        </p>
                        <p>
                          <Link href="/schedule">Open schedule</Link>
                        </p>
                      </>
                    ) : (
                      <EmptyState
                        title="None scheduled"
                        action={
                          <Button
                            type="button"
                            size="sm"
                            onClick={() =>
                              router.push(`/schedule?patient=${encodeURIComponent(patient.id)}`)
                            }
                          >
                            Book
                          </Button>
                        }
                      />
                    )}
                  </Card>
                  <Card title="Last visit">
                    <p>
                      <strong>
                        {overview.last_visit_at
                          ? fmtWhen(overview.last_visit_at)
                          : "None recorded"}
                      </strong>
                    </p>
                    <p className="hos-helper">{encounters.length} encounter(s) on file</p>
                  </Card>
                  <Card title="Outstanding balance">
                    <p>
                      <MoneyDisplay
                        amount={overview.outstanding_balance}
                        currency={overview.currency}
                      />
                    </p>
                    {credit ? (
                      <p className="hos-helper">
                        Credit on file: <MoneyDisplay amount={credit} />
                      </p>
                    ) : null}
                  </Card>
                  <Card title="Follow-ups">
                    <p>
                      <strong>{overview.open_followups ?? 0}</strong> open
                      {(overview.overdue_followups ?? 0) > 0
                        ? ` · ${overview.overdue_followups} overdue`
                        : ""}
                    </p>
                    <p className="hos-helper">
                      Next due:{" "}
                      {overview.follow_up_due
                        ? new Date(overview.follow_up_due).toLocaleDateString()
                        : "None"}
                    </p>
                    <p>
                      <Link href="/follow-ups">Follow-up workspace</Link>
                    </p>
                  </Card>
                </div>
              ) : (
                <EmptyState title="Overview unavailable" />
              )}
              <Card title="Relationship snapshot">
                <p className="hos-helper">
                  {appointments.length} appointments · {encounters.length} encounters ·{" "}
                  {plans.length} treatment plans · {invoices.length} invoices · {followUps.length}{" "}
                  follow-ups
                </p>
                <p className="hos-helper">
                  Use Timeline for chronological history. Clinical, Care, and Billing tabs hold
                  domain detail. Internal clinical note bodies stay on encounter screens.
                </p>
              </Card>
            </TabsContent>

            <TabsContent value="timeline">
              <Card title="Chronological history">
                <div className="hos-quick-actions" role="group" aria-label="Filter timeline by category">
                  {TIMELINE_CATEGORIES.map((c) => (
                    <Button
                      key={c.value || "all"}
                      type="button"
                      size="sm"
                      variant={timelineCategory === c.value ? "primary" : "secondary"}
                      onClick={() => setTimelineCategory(c.value)}
                    >
                      {c.label}
                    </Button>
                  ))}
                </div>
                {timelineLoading && timeline.length === 0 ? (
                  <LoadingState label="Loading timeline" />
                ) : timeline.length === 0 ? (
                  <EmptyState title="No timeline events yet" />
                ) : (
                  <Table
                    caption="Patient timeline"
                    density="compact"
                    columns={
                      <>
                        <Th>When</Th>
                        <Th>Event</Th>
                        <Th>Category</Th>
                        <Th>Status</Th>
                      </>
                    }
                  >
                    {timeline.map((ev) => (
                      <tr key={ev.event_id}>
                        <Td>{fmtWhen(ev.occurred_at)}</Td>
                        <Td>
                          {ev.href ? <Link href={ev.href}>{ev.title}</Link> : ev.title}
                          {ev.summary ? (
                            <>
                              <br />
                              <span className="hos-helper">{ev.summary}</span>
                            </>
                          ) : null}
                        </Td>
                        <Td>{ev.category}</Td>
                        <Td>{ev.status ? <Status value={ev.status} /> : "—"}</Td>
                      </tr>
                    ))}
                  </Table>
                )}
                {timelineCursor ? (
                  <p>
                    <Button
                      type="button"
                      variant="secondary"
                      loading={timelineLoading}
                      onClick={() => loadTimeline(false, timelineCursor)}
                    >
                      Load more
                    </Button>
                  </p>
                ) : null}
              </Card>
            </TabsContent>

            <TabsContent value="clinical">
              <Card title="Appointments">
                {appointments.length === 0 ? (
                  <EmptyState
                    title="No appointments"
                    action={
                      <Button
                        type="button"
                        size="sm"
                        onClick={() =>
                          router.push(`/schedule?patient=${encodeURIComponent(patient.id)}`)
                        }
                      >
                        Book
                      </Button>
                    }
                  />
                ) : (
                  <Table
                    caption="Patient appointments"
                    density="compact"
                    columns={
                      <>
                        <Th>When</Th>
                        <Th>Token</Th>
                        <Th>Status</Th>
                      </>
                    }
                  >
                    {appointments.map((a) => (
                      <tr key={a.id}>
                        <Td>{fmtWhen(a.start_at)}</Td>
                        <Td>{a.queue_token ?? "—"}</Td>
                        <Td>
                          <Status value={a.status} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
              <Card title="Encounters">
                {encounters.length === 0 ? (
                  <EmptyState title="No encounters" />
                ) : (
                  <Table
                    caption="Patient encounters"
                    density="compact"
                    columns={
                      <>
                        <Th>Opened</Th>
                        <Th>Status</Th>
                      </>
                    }
                  >
                    {encounters.map((e) => (
                      <tr key={e.id}>
                        <Td>
                          <Link href={`/encounters/${e.id}`}>{fmtWhen(e.opened_at)}</Link>
                        </Td>
                        <Td>
                          <Status value={e.status} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
              <Card title="Treatment plans">
                {plans.length === 0 ? (
                  <EmptyState title="No treatment plans" />
                ) : (
                  <Table
                    caption="Treatment plans"
                    density="compact"
                    columns={
                      <>
                        <Th>Plan</Th>
                        <Th>Status</Th>
                      </>
                    }
                  >
                    {plans.map((p) => (
                      <tr key={p.id}>
                        <Td>
                          <Link href={`/dental/plans/${p.id}`}>Plan v{p.version}</Link>
                        </Td>
                        <Td>
                          <Status value={p.status} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
              <Card title="Recalls">
                {recalls.length === 0 ? (
                  <EmptyState title="No recalls" />
                ) : (
                  <Table
                    caption="Recalls"
                    density="compact"
                    columns={
                      <>
                        <Th>Due</Th>
                        <Th>Reason</Th>
                        <Th>Status</Th>
                      </>
                    }
                  >
                    {recalls.map((r) => (
                      <tr key={r.id}>
                        <Td>{r.due_date}</Td>
                        <Td>{r.reason}</Td>
                        <Td>
                          <Status value={r.status} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="care">
              <Card title="Follow-ups">
                {followUps.length === 0 ? (
                  <EmptyState title="No follow-ups">
                    <Link href="/follow-ups">Open follow-up workspace</Link>
                  </EmptyState>
                ) : (
                  <Table
                    caption="Patient follow-ups"
                    density="compact"
                    columns={
                      <>
                        <Th>Due</Th>
                        <Th>Reason</Th>
                        <Th>Status</Th>
                      </>
                    }
                  >
                    {followUps.map((fu) => (
                      <tr key={fu.id}>
                        <Td>{fmtWhen(fu.due_at)}</Td>
                        <Td>
                          {fu.reason} · {fu.category}
                        </Td>
                        <Td>
                          <Status value={fu.status} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
              <Card title="Communication preferences">
                {consents.length === 0 ? (
                  <EmptyState title="No recorded preferences">
                    Missing consent means not eligible (fail closed).
                  </EmptyState>
                ) : (
                  <Table
                    caption="Communication consents"
                    density="compact"
                    columns={
                      <>
                        <Th>Channel</Th>
                        <Th>Purpose</Th>
                        <Th>Status</Th>
                      </>
                    }
                  >
                    {consents.map((c) => (
                      <tr key={c.id}>
                        <Td>{c.channel}</Td>
                        <Td>{c.purpose}</Td>
                        <Td>
                          <Status value={c.status} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
                <p>
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={async () => {
                      const t = getSelectedTenant();
                      if (!t) return;
                      try {
                        await api.post(
                          `/api/v1/tenants/${t}/communication-consents`,
                          {
                            patient_id: id,
                            channel: "whatsapp",
                            purpose: "care_followup",
                            status: "granted",
                          },
                          t,
                        );
                        load();
                      } catch (err) {
                        setError((err as Error).message);
                      }
                    }}
                  >
                    Record WhatsApp care-follow-up consent
                  </Button>
                </p>
              </Card>
              <Card title="WhatsApp click-to-chat">
                <Field label="Purpose" htmlFor="wa-purpose">
                  {({ describedBy }) => (
                    <Select
                      id="wa-purpose"
                      aria-describedby={describedBy}
                      value={waPurpose}
                      onChange={(e) => setWaPurpose(e.target.value)}
                      options={[
                        { value: "care_followup", label: "Care follow-up" },
                        { value: "appointment_reminder", label: "Appointment reminder" },
                        { value: "administrative", label: "Administrative" },
                      ]}
                    />
                  )}
                </Field>
                {!patient.phone ? (
                  <p className="hos-helper">Add a phone number in Details before WhatsApp.</p>
                ) : null}
                <WhatsAppShareAction
                  title="Prepare WhatsApp message"
                  contextLabel={`Care outreach for ${patient.display_name}. Requires WhatsApp consent for ${waPurpose}. No clinical notes in the message.`}
                  initialPhone={patient.phone}
                  initialMessage={`Hello from ${clinicName}. This is a care message from your clinic. Please reply in WhatsApp if you have questions.`}
                  linkToCopy={appOrigin() || portalHomeShareUrl()}
                  disabled={!patient.phone}
                  confirmLabel={`I confirm this opens WhatsApp for ${patient.display_name} (${waPurpose}). Opening is not a send.`}
                  resolveOpenUrl={async ({ phone: _phone, message }) => {
                    const t = getSelectedTenant();
                    if (!t) throw new Error("Select a workspace first");
                    const link = await api.post<{ url: string }>(
                      `/api/v1/tenants/${t}/whatsapp-link`,
                      {
                        patient_id: id,
                        purpose: waPurpose,
                        message,
                        require_consent: true,
                      },
                      t,
                    );
                    return link.url;
                  }}
                  onOpened={() => {
                    const t = getSelectedTenant();
                    if (!t) return;
                    const outcome = window.confirm(
                      "Did you complete the WhatsApp interaction? OK = contacted, Cancel = skip logging.",
                    );
                    if (!outcome) return;
                    void api
                      .post(
                        `/api/v1/tenants/${t}/communication-logs`,
                        {
                          patient_id: id,
                          channel: "whatsapp",
                          purpose: waPurpose,
                          outcome: "contacted",
                          note: "Staff-confirmed after wa.me open",
                        },
                        t,
                      )
                      .then(() => load())
                      .catch((err: Error) => setError(err.message));
                  }}
                />
              </Card>
              <Card title="Communication history">
                {commLogs.length === 0 ? (
                  <EmptyState title="No communications logged" />
                ) : (
                  <Table
                    caption="Communication log"
                    density="compact"
                    columns={
                      <>
                        <Th>When</Th>
                        <Th>Channel</Th>
                        <Th>Outcome</Th>
                      </>
                    }
                  >
                    {commLogs.map((l) => (
                      <tr key={l.id}>
                        <Td>{fmtWhen(l.occurred_at)}</Td>
                        <Td>
                          {l.channel} · {l.purpose}
                        </Td>
                        <Td>
                          <Status value={l.outcome} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="billing">
              <Card title="Invoices">
                {invoices.length === 0 ? (
                  <EmptyState title="No invoices" />
                ) : (
                  <Table
                    caption="Invoices"
                    density="compact"
                    columns={
                      <>
                        <Th>Invoice</Th>
                        <Th>Status</Th>
                        <Th numeric>Total</Th>
                        <Th numeric>Outstanding</Th>
                      </>
                    }
                  >
                    {invoices.map((i) => (
                      <tr key={i.id}>
                        <Td>
                          <Link href={`/billing/invoices/${i.id}`}>{i.id.slice(0, 8)}…</Link>
                        </Td>
                        <Td>
                          <Status value={i.status} />
                        </Td>
                        <Td numeric>
                          <MoneyDisplay amount={i.grand_total} currency={i.currency} />
                        </Td>
                        <Td numeric>
                          <MoneyDisplay amount={i.outstanding_amount} currency={i.currency} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
              <Card title="Payments">
                {payments.length === 0 ? (
                  <EmptyState title="No payments" />
                ) : (
                  <Table
                    caption="Payments"
                    density="compact"
                    columns={
                      <>
                        <Th>Method</Th>
                        <Th>Status</Th>
                        <Th numeric>Amount</Th>
                      </>
                    }
                  >
                    {payments.map((p) => (
                      <tr key={p.id}>
                        <Td>{p.method}</Td>
                        <Td>
                          <Status value={p.status} />
                        </Td>
                        <Td numeric>
                          <MoneyDisplay amount={p.amount} currency={p.currency} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>
            </TabsContent>

            <TabsContent value="details">
              <Card title="Patient portal enrollment">
                <p className="hos-helper">
                  Staff with <code>staff.manage</code> can link a login email to this patient. New
                  portal users receive an unusable random password and must set one via{" "}
                  <Link href="/password-reset">password reset</Link>. Enrollment success is
                  confirmed only by the server. Do not enroll real patients in non-production.
                </p>
                {portalMsg ? (
                  <Alert tone="success" title="Portal enrollment">
                    {portalMsg}
                  </Alert>
                ) : null}
                <form
                  onSubmit={async (e) => {
                    e.preventDefault();
                    const t = getSelectedTenant();
                    if (!t || !patient) return;
                    setPortalBusy(true);
                    setPortalMsg("");
                    setPortalShare(null);
                    setError("");
                    const enrolledEmail = portalEmail.trim();
                    try {
                      const link = await api.post<{
                        id: string;
                        status: string;
                        user_id: string;
                      }>(
                        `/api/v1/tenants/${t}/portal-links`,
                        {
                          email: enrolledEmail,
                          patient_id: patient.id,
                          display_name: patient.display_name,
                        },
                        t,
                      );
                      const resetUrl = portalActivationShareUrl();
                      const portalUrl = portalHomeShareUrl();
                      setPortalMsg(
                        `Linked (${link.status}). Share password setup via WhatsApp or Copy link — no clinical data included.`,
                      );
                      setPortalShare({
                        email: enrolledEmail,
                        resetUrl,
                        phone: patient.phone ?? "",
                        message: portalEnrollMessage({
                          clinicName,
                          email: enrolledEmail,
                          resetUrl,
                          portalUrl,
                        }),
                      });
                      setPortalEmail("");
                    } catch (err) {
                      setError((err as Error).message);
                    } finally {
                      setPortalBusy(false);
                    }
                  }}
                >
                  <Field
                    label="Portal login email"
                    htmlFor="portal-email"
                    required
                    description="Must be the email the patient will use to sign in."
                  >
                    {() => (
                      <Input
                        id="portal-email"
                        type="email"
                        value={portalEmail}
                        onChange={(e) => setPortalEmail(e.target.value)}
                        required
                        autoComplete="off"
                      />
                    )}
                  </Field>
                  <p>
                    <Button type="submit" loading={portalBusy}>
                      Enroll patient portal access
                    </Button>
                  </p>
                </form>
                {portalShare ? (
                  <WhatsAppShareAction
                    title="Share portal activation"
                    contextLabel={`Enrollment for ${portalShare.email}. Shares password-reset and portal URLs only — no tokens or clinical notes.`}
                    initialPhone={portalShare.phone}
                    initialMessage={portalShare.message}
                    linkToCopy={portalShare.resetUrl}
                  />
                ) : null}
              </Card>
              <Card title="Contact & demographics">
                <form onSubmit={save}>
                  <Field label="Display name" htmlFor="p-name" required>
                    {() => (
                      <Input
                        id="p-name"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        required
                        minLength={2}
                      />
                    )}
                  </Field>
                  <Field label="Phone" htmlFor="p-phone">
                    {() => (
                      <Input id="p-phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
                    )}
                  </Field>
                  <Field label="Email" htmlFor="p-email">
                    {() => (
                      <Input
                        id="p-email"
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                      />
                    )}
                  </Field>
                  <Field label="Date of birth" htmlFor="p-dob">
                    {() => (
                      <Input
                        id="p-dob"
                        type="date"
                        value={dob}
                        onChange={(e) => setDob(e.target.value)}
                      />
                    )}
                  </Field>
                  <Field label="Emergency contact name" htmlFor="p-en">
                    {() => (
                      <Input
                        id="p-en"
                        value={emergName}
                        onChange={(e) => setEmergName(e.target.value)}
                      />
                    )}
                  </Field>
                  <Field label="Emergency contact phone" htmlFor="p-ep">
                    {() => (
                      <Input
                        id="p-ep"
                        value={emergPhone}
                        onChange={(e) => setEmergPhone(e.target.value)}
                      />
                    )}
                  </Field>
                  <p>
                    <Button type="submit" loading={saving}>
                      Save details
                    </Button>
                  </p>
                </form>
              </Card>
            </TabsContent>
          </Tabs>
        </>
      ) : null}
    </Shell>
  );
}
