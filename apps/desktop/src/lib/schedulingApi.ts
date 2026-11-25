import { apiFetch } from "./api";

export type AppointmentStatus =
  | "scheduled"
  | "confirmed"
  | "checked_in"
  | "completed"
  | "cancelled"
  | "no_show";

export type Appointment = {
  id: string;
  tenant_id: string;
  location_id: string;
  patient_id: string;
  practitioner_id: string;
  start_at: string;
  end_at: string;
  timezone?: string | null;
  status: AppointmentStatus;
  notes: string | null;
  queue_token: number | null;
  queue_date?: string | null;
  cancelled_at?: string | null;
  cancelled_by?: string | null;
  cancel_reason?: string | null;
  created_at?: string;
  updated_at?: string;
};

export type AppointmentListResponse = {
  items: Appointment[];
  next_cursor?: string | null;
};

export type ReceptionQueueResponse = {
  location_id: string;
  queue_date: string;
  timezone: string;
  waiting: Appointment[];
  checked_in: Appointment[];
  completed: Appointment[];
  no_show: Appointment[];
  cancelled: Appointment[];
};

export type Practitioner = {
  id: string;
  display_name: string;
  is_active?: boolean;
  verification_status?: string;
};

export type Slot = {
  start_at: string;
  end_at: string;
};

export type AvailabilityResponse = {
  practitioner_id: string;
  location_id: string;
  timezone: string;
  date: string;
  slot_minutes: number;
  slots: Slot[];
};

export type AppointmentCreate = {
  patient_id: string;
  practitioner_id: string;
  location_id: string;
  start: string;
  duration_minutes: number;
  notes?: string | null;
  timezone?: string | null;
  walk_in?: boolean;
};

/** Backend TRANSITIONS matrix — frontend must not invent others. */
export const STATUS_TRANSITIONS: Record<
  AppointmentStatus,
  readonly AppointmentStatus[]
> = {
  scheduled: ["confirmed", "checked_in", "cancelled", "no_show"],
  confirmed: ["checked_in", "cancelled", "no_show"],
  checked_in: ["completed", "cancelled"],
  completed: [],
  cancelled: [],
  no_show: [],
};

export function allowedTransitions(
  status: AppointmentStatus,
): readonly AppointmentStatus[] {
  return STATUS_TRANSITIONS[status] ?? [];
}

export async function listAppointments(
  tenantId: string,
  opts: {
    locationId?: string;
    practitionerId?: string;
    patientId?: string;
    status?: string;
    startFrom?: string;
    startTo?: string;
    limit?: number;
    cursor?: string;
  } = {},
): Promise<Appointment[]> {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 200));
  if (opts.locationId) params.set("location_id", opts.locationId);
  if (opts.practitionerId) params.set("practitioner_id", opts.practitionerId);
  if (opts.patientId) params.set("patient_id", opts.patientId);
  if (opts.status) params.set("status", opts.status);
  if (opts.startFrom) params.set("start_from", opts.startFrom);
  if (opts.startTo) params.set("start_to", opts.startTo);
  if (opts.cursor) params.set("cursor", opts.cursor);
  const res = await apiFetch(
    `/api/v1/tenants/${tenantId}/appointments?${params}`,
    { tenantId },
  );
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status !== 200 || !res.json) return [];
  const data = res.json as AppointmentListResponse | Appointment[];
  if (Array.isArray(data)) return data;
  return Array.isArray(data.items) ? data.items : [];
}

export async function createAppointment(
  tenantId: string,
  body: AppointmentCreate,
): Promise<Appointment> {
  const res = await apiFetch(`/api/v1/tenants/${tenantId}/appointments`, {
    method: "POST",
    tenantId,
    body,
  });
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status === 409) throw new Error("conflict");
  if (res.status === 422) {
    const detail =
      res.json && typeof res.json === "object" && "detail" in res.json
        ? JSON.stringify((res.json as { detail: unknown }).detail)
        : "validation_failed";
    throw new Error(detail);
  }
  if (res.status !== 200 && res.status !== 201) {
    const detail =
      res.json && typeof res.json === "object" && "detail" in res.json
        ? String((res.json as { detail: unknown }).detail)
        : "create_failed";
    throw new Error(detail);
  }
  return res.json as Appointment;
}

export async function rescheduleAppointment(
  tenantId: string,
  appointmentId: string,
  body: { start: string; duration_minutes: number },
): Promise<Appointment> {
  const res = await apiFetch(
    `/api/v1/tenants/${tenantId}/appointments/${appointmentId}`,
    { method: "PATCH", tenantId, body },
  );
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status === 409) throw new Error("conflict");
  if (res.status === 422) throw new Error("cannot_reschedule");
  if (res.status !== 200 || !res.json) throw new Error("reschedule_failed");
  return res.json as Appointment;
}

export async function updateAppointmentStatus(
  tenantId: string,
  appointmentId: string,
  status: AppointmentStatus,
): Promise<Appointment> {
  const res = await apiFetch(
    `/api/v1/tenants/${tenantId}/appointments/${appointmentId}/status`,
    { method: "POST", tenantId, body: { status } },
  );
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status === 422) throw new Error("invalid_transition");
  if (res.status !== 200 || !res.json) throw new Error("status_failed");
  return res.json as Appointment;
}

export async function cancelAppointment(
  tenantId: string,
  appointmentId: string,
  reason?: string,
): Promise<Appointment> {
  const res = await apiFetch(
    `/api/v1/tenants/${tenantId}/appointments/${appointmentId}/cancel`,
    { method: "POST", tenantId, body: { reason: reason ?? null } },
  );
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status !== 200 || !res.json) throw new Error("cancel_failed");
  return res.json as Appointment;
}

export async function fetchReceptionQueue(
  tenantId: string,
  locationId: string,
  opts: { day?: string; practitionerId?: string } = {},
): Promise<ReceptionQueueResponse> {
  const params = new URLSearchParams();
  if (opts.day) params.set("day", opts.day);
  if (opts.practitionerId) params.set("practitioner_id", opts.practitionerId);
  const q = params.toString();
  const res = await apiFetch(
    `/api/v1/tenants/${tenantId}/locations/${locationId}/reception-queue${q ? `?${q}` : ""}`,
    { tenantId },
  );
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status !== 200 || !res.json) {
    return {
      location_id: locationId,
      queue_date: opts.day ?? "",
      timezone: "UTC",
      waiting: [],
      checked_in: [],
      completed: [],
      no_show: [],
      cancelled: [],
    };
  }
  return res.json as ReceptionQueueResponse;
}

export async function listPractitioners(
  tenantId: string,
): Promise<Practitioner[]> {
  const res = await apiFetch(`/api/v1/tenants/${tenantId}/practitioners`, {
    tenantId,
  });
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return (res.json as Practitioner[]).filter((p) => p.is_active !== false);
}

/** Prefer approved practitioners for clinical writes (encounter.open). */
export function approvedPractitioners(rows: Practitioner[]): Practitioner[] {
  const approved = rows.filter((p) => p.verification_status === "approved");
  return approved.length ? approved : rows;
}

export async function fetchAvailability(
  tenantId: string,
  opts: {
    practitionerId: string;
    locationId: string;
    day: string;
  },
): Promise<AvailabilityResponse | null> {
  const params = new URLSearchParams({
    practitioner_id: opts.practitionerId,
    location_id: opts.locationId,
    day: opts.day,
  });
  const res = await apiFetch(
    `/api/v1/tenants/${tenantId}/availability?${params}`,
    { tenantId },
  );
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  if (res.status !== 200 || !res.json) return null;
  return res.json as AvailabilityResponse;
}

export function flattenQueue(
  queue: ReceptionQueueResponse,
): Array<Appointment & { bucket: string }> {
  const rows: Array<Appointment & { bucket: string }> = [];
  for (const a of queue.waiting) rows.push({ ...a, bucket: "waiting" });
  for (const a of queue.checked_in) rows.push({ ...a, bucket: "checked_in" });
  for (const a of queue.completed) rows.push({ ...a, bucket: "completed" });
  for (const a of queue.no_show) rows.push({ ...a, bucket: "no_show" });
  for (const a of queue.cancelled) rows.push({ ...a, bucket: "cancelled" });
  return rows;
}
