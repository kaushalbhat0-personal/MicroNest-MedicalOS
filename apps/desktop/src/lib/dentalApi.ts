import { apiFetch } from "./api";

export type DentalCondition = {
  id: string;
  code: string;
  display: string;
  is_active: boolean;
};

export type DentalProcedureCatalog = {
  id: string;
  code: string;
  display: string;
  description: string | null;
  specialty: string;
  external_code: string | null;
  is_active: boolean;
};

export type ToothFinding = {
  id: string;
  tenant_id: string;
  encounter_id: string;
  practitioner_id: string;
  tooth: number;
  condition_code: string;
  condition_display: string;
  surfaces: string[];
  status: string;
  details: string | null;
  created_at: string;
  updated_at: string;
};

export type PlanItem = {
  id: string;
  procedure_code: string;
  procedure_display: string;
  tooth: number | null;
  surface: string | null;
  sequence: number;
  status: string;
  notes: string | null;
};

export type TreatmentPlan = {
  id: string;
  tenant_id: string;
  patient_id: string;
  encounter_id: string | null;
  practitioner_id: string;
  status: string;
  version: number;
  notes: string | null;
  items: PlanItem[];
  created_at: string;
  updated_at: string;
};

export type ProcedureRecord = {
  id: string;
  tenant_id: string;
  encounter_id: string;
  practitioner_id: string;
  procedure_code: string;
  procedure_display: string;
  plan_item_id: string | null;
  tooth: number | null;
  surface: string | null;
  status: string;
  notes: string | null;
  performed_at: string | null;
  created_at: string;
  updated_at: string;
};

export type DentalConsent = {
  id: string;
  tenant_id: string;
  plan_id: string | null;
  procedure_record_id: string | null;
  status: string;
  consenter_name: string;
  consenter_relation: string | null;
  document_ref: string | null;
  decided_by: string | null;
  decided_at: string | null;
  created_at: string;
  updated_at: string;
};

/** FDI permanent dentition — mirrors backend validate_tooth / UI Odontogram. */
export const FDI_PERMANENT = [
  11, 12, 13, 14, 15, 16, 17, 18, 21, 22, 23, 24, 25, 26, 27, 28, 31, 32, 33, 34,
  35, 36, 37, 38, 41, 42, 43, 44, 45, 46, 47, 48,
] as const;

export const DENTAL_SURFACES = [
  "mesial",
  "distal",
  "occlusal",
  "incisal",
  "buccal",
  "labial",
  "lingual",
  "palatal",
] as const;

export type ChartToothState = "finding" | "planned" | "completed";

function detailMessage(json: unknown, fallback: string): string {
  if (json && typeof json === "object" && "detail" in json) {
    const d = (json as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    return JSON.stringify(d);
  }
  return fallback;
}

async function dentalFetch(
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

export function isFdiPermanent(tooth: number): boolean {
  return (FDI_PERMANENT as readonly number[]).includes(tooth);
}

export function isDentalSurface(surface: string): boolean {
  return (DENTAL_SURFACES as readonly string[]).includes(surface.trim().toLowerCase());
}

/**
 * Derive odontogram projection from backend findings + procedure records.
 * Precedence: active finding > in_progress/planned procedure > completed.
 * Primary dentition and missing/restored-without-finding are not invented.
 */
export function deriveOdontogramStates(
  findings: Array<{ tooth: number; status: string }>,
  procedures: Array<{ tooth: number | null; status: string }> = [],
): Record<number, ChartToothState> {
  const states: Record<number, ChartToothState> = {};
  for (const p of procedures) {
    if (p.tooth == null || !isFdiPermanent(p.tooth)) continue;
    if (p.status === "completed") states[p.tooth] = "completed";
    else if (p.status === "planned" || p.status === "in_progress") {
      if (states[p.tooth] !== "completed") states[p.tooth] = "planned";
    }
  }
  for (const f of findings) {
    if (!isFdiPermanent(f.tooth)) continue;
    if (f.status === "active") states[f.tooth] = "finding";
  }
  return states;
}

export const PLAN_ITEM_NEXT: Record<string, string[]> = {
  proposed: ["planned", "cancelled"],
  planned: ["in_progress", "cancelled"],
  in_progress: ["completed", "cancelled"],
};

export const PROCEDURE_RECORD_NEXT: Record<string, string[]> = {
  planned: ["in_progress", "cancelled"],
  in_progress: ["completed", "cancelled"],
};

export function procedureTransitionNeedsConsent(toStatus: string): boolean {
  return toStatus === "in_progress" || toStatus === "completed";
}

export async function listDentalConditions(
  tenantId: string,
): Promise<DentalCondition[]> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/dental-conditions`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return (res.json as DentalCondition[]).filter((c) => c.is_active !== false);
}

export async function listDentalProcedureCatalog(
  tenantId: string,
): Promise<DentalProcedureCatalog[]> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/dental-procedures`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return (res.json as DentalProcedureCatalog[]).filter((p) => p.is_active !== false);
}

export async function listToothFindings(
  tenantId: string,
  encounterId: string,
): Promise<ToothFinding[]> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/encounters/${encounterId}/tooth-findings`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as ToothFinding[];
}

export async function recordToothFinding(
  tenantId: string,
  encounterId: string,
  body: {
    tooth: number;
    condition_code: string;
    surfaces?: string[];
    details?: string | null;
  },
): Promise<ToothFinding> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/encounters/${encounterId}/tooth-findings`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "finding_failed"));
  }
  return res.json as ToothFinding;
}

export async function resolveToothFinding(
  tenantId: string,
  findingId: string,
): Promise<ToothFinding> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/tooth-findings/${findingId}/resolve`,
    tenantId,
    { method: "POST", body: {} },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "resolve_failed"));
  return res.json as ToothFinding;
}

export async function listTreatmentPlans(
  tenantId: string,
  patientId: string,
): Promise<TreatmentPlan[]> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/treatment-plans?patient_id=${patientId}`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as TreatmentPlan[];
}

export async function getTreatmentPlan(
  tenantId: string,
  planId: string,
): Promise<TreatmentPlan> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/treatment-plans/${planId}`,
    tenantId,
  );
  if (res.status === 404) throw new Error("not_found");
  if (res.status !== 200 || !res.json) throw new Error("load_failed");
  return res.json as TreatmentPlan;
}

export async function createTreatmentPlan(
  tenantId: string,
  body: {
    patient_id: string;
    encounter_id?: string | null;
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
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/treatment-plans`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "plan_create_failed"));
  }
  return res.json as TreatmentPlan;
}

export async function addPlanItem(
  tenantId: string,
  planId: string,
  body: {
    procedure_code: string;
    tooth?: number | null;
    surface?: string | null;
    sequence?: number;
    notes?: string | null;
  },
): Promise<PlanItem> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/treatment-plans/${planId}/items`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "plan_item_failed"));
  }
  return res.json as PlanItem;
}

export async function activatePlan(
  tenantId: string,
  planId: string,
): Promise<TreatmentPlan> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/treatment-plans/${planId}/activate`,
    tenantId,
    { method: "POST", body: {} },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "activate_failed"));
  return res.json as TreatmentPlan;
}

export async function completePlan(
  tenantId: string,
  planId: string,
): Promise<TreatmentPlan> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/treatment-plans/${planId}/complete`,
    tenantId,
    { method: "POST", body: {} },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "complete_failed"));
  return res.json as TreatmentPlan;
}

export async function cancelPlan(
  tenantId: string,
  planId: string,
): Promise<TreatmentPlan> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/treatment-plans/${planId}/cancel`,
    tenantId,
    { method: "POST", body: {} },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "cancel_failed"));
  return res.json as TreatmentPlan;
}

export async function transitionPlanItem(
  tenantId: string,
  itemId: string,
  status: string,
): Promise<PlanItem> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/plan-items/${itemId}/status`,
    tenantId,
    { method: "POST", body: { status } },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "item_status_failed"));
  return res.json as PlanItem;
}

export async function listProcedureRecords(
  tenantId: string,
  encounterId: string,
): Promise<ProcedureRecord[]> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/encounters/${encounterId}/procedure-records`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as ProcedureRecord[];
}

export async function createProcedureRecord(
  tenantId: string,
  encounterId: string,
  body: {
    procedure_code: string;
    plan_item_id?: string | null;
    tooth?: number | null;
    surface?: string | null;
    notes?: string | null;
  },
): Promise<ProcedureRecord> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/encounters/${encounterId}/procedure-records`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "procedure_record_failed"));
  }
  return res.json as ProcedureRecord;
}

export async function transitionProcedureRecord(
  tenantId: string,
  recordId: string,
  status: string,
): Promise<ProcedureRecord> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/procedure-records/${recordId}/status`,
    tenantId,
    { method: "POST", body: { status } },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "procedure_status_failed"));
  return res.json as ProcedureRecord;
}

export async function createDentalConsent(
  tenantId: string,
  body: {
    plan_id?: string | null;
    procedure_record_id?: string | null;
    consenter_name: string;
    consenter_relation?: string | null;
    document_ref?: string | null;
  },
): Promise<DentalConsent> {
  const res = await dentalFetch(`/api/v1/tenants/${tenantId}/consents`, tenantId, {
    method: "POST",
    body,
  });
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "consent_create_failed"));
  }
  return res.json as DentalConsent;
}

export async function decideDentalConsent(
  tenantId: string,
  consentId: string,
  decision: "granted" | "declined",
): Promise<DentalConsent> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/consents/${consentId}/decide`,
    tenantId,
    { method: "POST", body: { decision } },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "consent_decide_failed"));
  return res.json as DentalConsent;
}

export async function withdrawDentalConsent(
  tenantId: string,
  consentId: string,
): Promise<DentalConsent> {
  const res = await dentalFetch(
    `/api/v1/tenants/${tenantId}/consents/${consentId}/withdraw`,
    tenantId,
    { method: "POST", body: {} },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "consent_withdraw_failed"));
  return res.json as DentalConsent;
}
