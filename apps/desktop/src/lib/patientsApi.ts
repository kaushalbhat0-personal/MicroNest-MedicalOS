import { apiFetch } from "./api";

export type Patient = {
  id: string;
  tenant_id: string;
  display_name: string;
  phone: string | null;
  email: string | null;
  date_of_birth: string | null;
  emergency_contact_name: string | null;
  emergency_contact_phone: string | null;
  is_active: boolean;
  potential_duplicates?: string[];
};

export type PatientOverview = {
  patient_id: string;
  display_name: string;
  phone: string | null;
  email: string | null;
  date_of_birth: string | null;
  is_active: boolean;
  last_visit_at: string | null;
  next_appointment_at: string | null;
  next_appointment_id: string | null;
  outstanding_balance: string;
  currency: string;
  follow_up_due: string | null;
  open_followups: number;
  overdue_followups: number;
  completed_followups: number;
};

export type TimelineItem = {
  event_id: string;
  kind: string;
  category: string;
  occurred_at: string;
  title: string;
  summary: string | null;
  resource_type: string | null;
  resource_id: string | null;
  location_id: string | null;
  status: string | null;
  href: string | null;
};

export type TimelinePage = {
  items: TimelineItem[];
  next_cursor: string | null;
};

export type PatientCreate = {
  display_name: string;
  phone?: string | null;
  email?: string | null;
  date_of_birth?: string | null;
  emergency_contact_name?: string | null;
  emergency_contact_phone?: string | null;
};

export async function listPatients(
  tenantId: string,
  opts: { q?: string; limit?: number; activeOnly?: boolean } = {},
): Promise<Patient[]> {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 100));
  if (opts.q?.trim()) params.set("q", opts.q.trim());
  if (opts.activeOnly) params.set("active_only", "true");
  const res = await apiFetch(`/api/v1/tenants/${tenantId}/patients?${params}`, {
    tenantId,
  });
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as Patient[];
}

export async function createPatient(
  tenantId: string,
  body: PatientCreate,
): Promise<Patient> {
  const res = await apiFetch(`/api/v1/tenants/${tenantId}/patients`, {
    method: "POST",
    tenantId,
    body,
  });
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status !== 200 && res.status !== 201) {
    const detail =
      res.json && typeof res.json === "object" && "detail" in res.json
        ? String((res.json as { detail: unknown }).detail)
        : "create_failed";
    throw new Error(detail);
  }
  return res.json as Patient;
}

export async function getPatient(
  tenantId: string,
  patientId: string,
): Promise<Patient> {
  const res = await apiFetch(
    `/api/v1/tenants/${tenantId}/patients/${patientId}`,
    { tenantId },
  );
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status === 404) throw new Error("not_found");
  if (res.status !== 200 || !res.json) throw new Error("load_failed");
  return res.json as Patient;
}

export async function getPatientOverview(
  tenantId: string,
  patientId: string,
): Promise<PatientOverview> {
  const res = await apiFetch(
    `/api/v1/tenants/${tenantId}/patients/${patientId}/overview`,
    { tenantId },
  );
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status !== 200 || !res.json) throw new Error("overview_failed");
  return res.json as PatientOverview;
}

export async function getPatientTimeline(
  tenantId: string,
  patientId: string,
  opts: { category?: string; cursor?: string; limit?: number } = {},
): Promise<TimelinePage> {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 50));
  if (opts.category) params.set("category", opts.category);
  if (opts.cursor) params.set("cursor", opts.cursor);
  const res = await apiFetch(
    `/api/v1/tenants/${tenantId}/patients/${patientId}/timeline?${params}`,
    { tenantId },
  );
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status !== 200 || !res.json) return { items: [], next_cursor: null };
  return res.json as TimelinePage;
}

export async function updatePatient(
  tenantId: string,
  patientId: string,
  body: Partial<PatientCreate> & { is_active?: boolean },
): Promise<Patient> {
  const res = await apiFetch(
    `/api/v1/tenants/${tenantId}/patients/${patientId}`,
    { method: "PATCH", tenantId, body },
  );
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status !== 200 || !res.json) throw new Error("update_failed");
  return res.json as Patient;
}
