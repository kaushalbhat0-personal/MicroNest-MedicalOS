import { apiFetch } from "./api";

export type EncounterStatus = "open" | "closed";

export type Encounter = {
  id: string;
  tenant_id: string;
  patient_id: string;
  practitioner_id: string;
  location_id: string;
  appointment_id: string | null;
  chief_complaint: string | null;
  status: EncounterStatus;
  version: number;
  opened_at: string;
  closed_at: string | null;
  close_reason: string | null;
};

export type ClinicalNote = {
  id: string;
  encounter_id: string;
  author_id: string;
  note_type: string;
  chief_complaint: string | null;
  subjective: string | null;
  objective: string | null;
  assessment: string | null;
  plan: string | null;
  status: string;
  version: number;
  is_addendum: boolean;
  supersedes_id: string | null;
  superseded_by_id: string | null;
  created_at: string;
};

export type Diagnosis = {
  id: string;
  diagnosis_code: string | null;
  free_text: string | null;
  is_primary: boolean;
  status: string;
  review_needed?: boolean;
  onset_date?: string | null;
};

export type DiagnosisCode = {
  code: string;
  display: string;
  icd10?: string | null;
  snomed?: string | null;
};

export type PrescriptionItem = {
  id?: string;
  medication_code: string;
  medication_name?: string;
  dose: string;
  route: string;
  frequency: string;
  duration_days?: number | null;
  quantity?: number | null;
  instructions: string;
  line_no?: number;
};

export type Prescription = {
  id: string;
  encounter_id: string;
  prescribed_by: string;
  status: string;
  version: number;
  items: PrescriptionItem[];
  signed_at?: string | null;
};

export type Medication = {
  code: string;
  name: string;
  generic_name?: string | null;
  strength?: string | null;
  dosage_form?: string | null;
  is_active?: boolean;
};

export type TreatmentPlan = {
  id: string;
  patient_id: string;
  encounter_id?: string | null;
  status: string;
  version?: number;
  notes?: string | null;
  items?: Array<{
    id: string;
    procedure_code: string;
    tooth?: number | null;
    status?: string;
  }>;
};

export type Estimate = {
  id: string;
  patient_id: string;
  status: string;
  treatment_plan_id?: string | null;
  encounter_id?: string | null;
  grand_total?: string;
  currency?: string;
};

export type FollowUp = {
  id: string;
  patient_id: string;
  due_at: string;
  reason: string;
  status: string;
  category: string;
  priority?: string;
};

export type Observation = {
  id: string;
  type_code: string;
  type_display?: string;
  value_numeric: number | string;
  value_text?: string | null;
  unit?: string;
  taken_at: string;
};

function detailMessage(json: unknown, fallback: string): string {
  if (json && typeof json === "object" && "detail" in json) {
    const d = (json as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    return JSON.stringify(d);
  }
  return fallback;
}

async function clinicalFetch(
  path: string,
  tenantId: string,
  init: { method?: string; body?: unknown } = {},
): Promise<{ status: number; json: unknown }> {
  const res = await apiFetch(path, {
    method: init.method,
    tenantId,
    body: init.body,
  });
  if (res.status === 401) throw new Error("session_expired");
  if (res.status === 403) throw new Error("forbidden");
  return res;
}

export async function listEncounters(
  tenantId: string,
  opts: {
    patientId?: string;
    practitionerId?: string;
    locationId?: string;
    status?: EncounterStatus;
    limit?: number;
  } = {},
): Promise<Encounter[]> {
  const params = new URLSearchParams();
  params.set("limit", String(opts.limit ?? 50));
  if (opts.patientId) params.set("patient_id", opts.patientId);
  if (opts.practitionerId) params.set("practitioner_id", opts.practitionerId);
  if (opts.locationId) params.set("location_id", opts.locationId);
  if (opts.status) params.set("status", opts.status);
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/encounters?${params}`,
    tenantId,
  );
  if (res.status !== 200 || !res.json) return [];
  const data = res.json as { items?: Encounter[] } | Encounter[];
  if (Array.isArray(data)) return data;
  return data.items ?? [];
}

export async function getEncounter(
  tenantId: string,
  encounterId: string,
): Promise<Encounter> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/encounters/${encounterId}`,
    tenantId,
  );
  if (res.status === 404) throw new Error("not_found");
  if (res.status !== 200 || !res.json) throw new Error("load_failed");
  return res.json as Encounter;
}

export async function openEncounter(
  tenantId: string,
  body: {
    patient_id: string;
    practitioner_id: string;
    location_id: string;
    appointment_id?: string | null;
    chief_complaint?: string | null;
  },
): Promise<Encounter> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/encounters`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status === 409) throw new Error(detailMessage(res.json, "conflict"));
  if (res.status === 422) throw new Error(detailMessage(res.json, "validation_failed"));
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "open_failed"));
  }
  return res.json as Encounter;
}

export async function closeEncounter(
  tenantId: string,
  encounterId: string,
  body: {
    note_waiver?: boolean;
    vitals_waiver?: boolean;
    reason?: string | null;
  } = {},
): Promise<Encounter> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/encounters/${encounterId}/close`,
    tenantId,
    {
      method: "POST",
      body: {
        note_waiver: body.note_waiver ?? false,
        vitals_waiver: body.vitals_waiver ?? false,
        reason: body.reason ?? null,
      },
    },
  );
  if (res.status === 409) throw new Error(detailMessage(res.json, "cannot_close"));
  if (res.status === 422) throw new Error(detailMessage(res.json, "close_validation"));
  if (res.status !== 200) throw new Error(detailMessage(res.json, "close_failed"));
  return res.json as Encounter;
}

export async function listNotes(
  tenantId: string,
  encounterId: string,
): Promise<ClinicalNote[]> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/encounters/${encounterId}/clinical-notes`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as ClinicalNote[];
}

export async function createNote(
  tenantId: string,
  encounterId: string,
  body: {
    note_type?: string;
    chief_complaint?: string | null;
    subjective?: string | null;
    objective?: string | null;
    assessment?: string | null;
    plan?: string | null;
  },
): Promise<ClinicalNote> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/encounters/${encounterId}/clinical-notes`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "note_create_failed"));
  }
  return res.json as ClinicalNote;
}

export async function finalizeNote(
  tenantId: string,
  noteId: string,
): Promise<ClinicalNote> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/clinical-notes/${noteId}/finalize`,
    tenantId,
    { method: "POST", body: {} },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "finalize_failed"));
  return res.json as ClinicalNote;
}

export async function amendNote(
  tenantId: string,
  noteId: string,
  body: {
    note_type?: string;
    chief_complaint?: string | null;
    subjective?: string | null;
    objective?: string | null;
    assessment?: string | null;
    plan?: string | null;
  },
): Promise<ClinicalNote> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/clinical-notes/${noteId}/amend`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "amend_failed"));
  }
  return res.json as ClinicalNote;
}

export async function listDiagnoses(
  tenantId: string,
  encounterId: string,
): Promise<Diagnosis[]> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/encounters/${encounterId}/diagnoses`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as Diagnosis[];
}

export async function createDiagnosis(
  tenantId: string,
  encounterId: string,
  body: {
    diagnosis_code?: string | null;
    free_text?: string | null;
    is_primary?: boolean;
    onset_date?: string | null;
  },
): Promise<Diagnosis> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/encounters/${encounterId}/diagnoses`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "diagnosis_failed"));
  }
  return res.json as Diagnosis;
}

export async function searchDiagnosisCodes(
  tenantId: string,
  q: string,
): Promise<DiagnosisCode[]> {
  // Catalog endpoint has no server-side q filter — filter locally.
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/diagnosis-codes`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  const rows = res.json as DiagnosisCode[];
  const needle = q.trim().toLowerCase();
  if (!needle) return rows.slice(0, 30);
  return rows
    .filter(
      (r) =>
        r.code.toLowerCase().includes(needle) ||
        r.display.toLowerCase().includes(needle) ||
        (r.icd10 ?? "").toLowerCase().includes(needle),
    )
    .slice(0, 30);
}

export async function listPrescriptions(
  tenantId: string,
  encounterId: string,
): Promise<Prescription[]> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/encounters/${encounterId}/prescriptions`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as Prescription[];
}

export async function createPrescription(
  tenantId: string,
  encounterId: string,
  items: PrescriptionItem[],
): Promise<Prescription> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/encounters/${encounterId}/prescriptions`,
    tenantId,
    {
      method: "POST",
      body: {
        items: items.map((i) => ({
          medication_code: i.medication_code,
          dose: i.dose,
          route: i.route,
          frequency: i.frequency,
          duration_days: i.duration_days ?? null,
          quantity: i.quantity ?? null,
          instructions: i.instructions,
        })),
      },
    },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "rx_create_failed"));
  }
  return res.json as Prescription;
}

export async function signPrescription(
  tenantId: string,
  prescriptionId: string,
): Promise<Prescription> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/prescriptions/${prescriptionId}/sign`,
    tenantId,
    { method: "POST", body: {} },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "sign_failed"));
  return res.json as Prescription;
}

export async function listMedications(
  tenantId: string,
  q?: string,
): Promise<Medication[]> {
  // Catalog endpoint has no server-side q — filter locally after fetch.
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/medications`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  let rows = (res.json as Medication[]).filter((m) => m.is_active !== false);
  const needle = q?.trim().toLowerCase();
  if (needle) {
    rows = rows.filter(
      (m) =>
        m.code.toLowerCase().includes(needle) ||
        m.name.toLowerCase().includes(needle) ||
        (m.generic_name ?? "").toLowerCase().includes(needle),
    );
  }
  return rows.slice(0, 50);
}

export async function listObservations(
  tenantId: string,
  encounterId: string,
): Promise<Observation[]> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/encounters/${encounterId}/observations`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as Observation[];
}

export async function createObservation(
  tenantId: string,
  encounterId: string,
  body: { type_code: string; value_numeric: number; value_text?: string | null },
): Promise<Observation> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/encounters/${encounterId}/observations`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "vitals_failed"));
  }
  return res.json as Observation;
}

export async function listTreatmentPlans(
  tenantId: string,
  patientId: string,
): Promise<TreatmentPlan[]> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/treatment-plans?patient_id=${patientId}`,
    tenantId,
  );
  if (res.status === 403) throw new Error("forbidden");
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as TreatmentPlan[];
}

export async function createTreatmentPlan(
  tenantId: string,
  body: {
    patient_id: string;
    encounter_id?: string | null;
    /** Required by schema; API still resolves actor practitioner server-side. */
    practitioner_id: string;
    notes?: string | null;
    items: Array<{
      procedure_code: string;
      tooth?: number | null;
      surface?: string | null;
      sequence?: number;
      notes?: string | null;
    }>;
  },
): Promise<TreatmentPlan> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/treatment-plans`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "plan_create_failed"));
  }
  return res.json as TreatmentPlan;
}

export async function listEstimates(
  tenantId: string,
  patientId: string,
): Promise<Estimate[]> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/estimates?patient_id=${patientId}&limit=50`,
    tenantId,
  );
  if (res.status === 403) return [];
  if (res.status !== 200 || !res.json) return [];
  const data = res.json as { items?: Estimate[] } | Estimate[];
  if (Array.isArray(data)) return data;
  return data.items ?? [];
}

export async function listFollowUps(
  tenantId: string,
  patientId: string,
): Promise<FollowUp[]> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/follow-ups?patient_id=${patientId}&limit=50`,
    tenantId,
  );
  if (res.status === 403) return [];
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as FollowUp[];
}

export async function createFollowUp(
  tenantId: string,
  body: {
    patient_id: string;
    location_id: string;
    due_at: string;
    reason: string;
    category?: string;
    source_type?: string;
    source_id?: string | null;
    priority?: string;
  },
): Promise<FollowUp> {
  const res = await clinicalFetch(
    `/api/v1/tenants/${tenantId}/follow-ups`,
    tenantId,
    {
      method: "POST",
      body: {
        category: "encounter",
        priority: "normal",
        source_type: "encounter",
        ...body,
      },
    },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "followup_failed"));
  }
  return res.json as FollowUp;
}

/** Backend encounter lifecycle — only open ↔ closed. */
export const ENCOUNTER_TRANSITIONS = {
  open: ["closed"] as const,
  closed: [] as const,
};
