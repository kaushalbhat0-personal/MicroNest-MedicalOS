import { apiFetch } from "./api";

export type StaffMember = {
  membership_id: string;
  user_id: string;
  email: string;
  display_name: string;
  role: string;
  permissions: string[];
  is_active: boolean;
  is_primary: boolean;
  location_ids: string[];
  designation: string | null;
  phone: string | null;
  employment_status: string;
  joined_at: string | null;
  notes: string | null;
};

export type Invitation = {
  id: string;
  email: string;
  role: string;
  status: string;
  location_ids: string[];
  expires_at: string;
  created_at: string;
  invited_by: string | null;
};

export type InviteCreated = {
  id: string;
  email: string;
  expires_at: string;
  token: string;
};

export type Role = {
  id: string;
  name: string;
  permissions: string[];
  is_seed: boolean;
};

export type PractitionerStatus = {
  id: string;
  display_name: string;
  verification_status: string;
};

export type VerificationItem = {
  practitioner_id: string;
  display_name: string;
  status: string;
  reason: string | null;
};

export type StaffSchedule = {
  id: string;
  membership_id: string;
  location_id: string;
  weekday: number;
  start_time: string;
  end_time: string;
  break_minutes: number;
  effective_from: string;
  effective_to: string | null;
  is_active: boolean;
};

export type Attendance = {
  id: string;
  membership_id: string;
  location_id: string;
  attendance_date: string;
  check_in_at: string;
  check_out_at: string | null;
  source: string;
  correction_reason: string | null;
  duration_minutes: number | null;
};

export type LeaveType = {
  id: string;
  name: string;
  is_active: boolean;
};

export type LeaveRequest = {
  id: string;
  membership_id: string;
  leave_type_id: string;
  leave_type_name: string;
  start_date: string;
  end_date: string;
  reason: string | null;
  status: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  created_at: string;
};

export const WEEKDAY_LABELS = [
  "Mon",
  "Tue",
  "Wed",
  "Thu",
  "Fri",
  "Sat",
  "Sun",
] as const;

function detailMessage(json: unknown, fallback: string): string {
  if (json && typeof json === "object" && "detail" in json) {
    const d = (json as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    return JSON.stringify(d);
  }
  return fallback;
}

async function staffFetch(
  path: string,
  tenantId: string | undefined,
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

export async function listStaff(
  tenantId: string,
  opts: { q?: string; activeOnly?: boolean; locationId?: string } = {},
): Promise<StaffMember[]> {
  const params = new URLSearchParams();
  if (opts.q?.trim()) params.set("q", opts.q.trim());
  if (opts.activeOnly) params.set("active_only", "true");
  if (opts.locationId) params.set("location_id", opts.locationId);
  const q = params.toString();
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/staff${q ? `?${q}` : ""}`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as StaffMember[];
}

export async function getStaff(
  tenantId: string,
  membershipId: string,
): Promise<StaffMember> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/staff/${membershipId}`,
    tenantId,
  );
  if (res.status === 404) throw new Error("not_found");
  if (res.status !== 200 || !res.json) throw new Error("load_failed");
  return res.json as StaffMember;
}

export async function updateStaff(
  tenantId: string,
  membershipId: string,
  body: Partial<{
    designation: string | null;
    phone: string | null;
    employment_status: string;
    joined_at: string | null;
    notes: string | null;
    location_ids: string[];
    role: string;
    is_active: boolean;
  }>,
): Promise<StaffMember> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/staff/${membershipId}`,
    tenantId,
    { method: "PATCH", body },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "update_failed"));
  return res.json as StaffMember;
}

export async function listInvitations(
  tenantId: string,
  status?: string,
): Promise<Invitation[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const q = params.toString();
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/invitations${q ? `?${q}` : ""}`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as Invitation[];
}

export async function createInvitation(
  tenantId: string,
  body: {
    email: string;
    role: string;
    location_ids?: string[] | null;
    ttl_days?: number;
  },
): Promise<InviteCreated> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/invites`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "invite_failed"));
  }
  return res.json as InviteCreated;
}

export async function revokeInvitation(
  tenantId: string,
  invitationId: string,
): Promise<void> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/invitations/${invitationId}/revoke`,
    tenantId,
    { method: "POST", body: {} },
  );
  if (res.status !== 200 && res.status !== 204) {
    throw new Error(detailMessage(res.json, "revoke_failed"));
  }
}

export async function listRoles(tenantId: string): Promise<Role[]> {
  const res = await staffFetch(`/api/v1/tenants/${tenantId}/roles`, tenantId);
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as Role[];
}

export async function listPractitionersStatus(
  tenantId: string,
): Promise<PractitionerStatus[]> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/practitioners`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as PractitionerStatus[];
}

export async function listVerificationQueue(
  tenantId: string,
): Promise<VerificationItem[]> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/verification`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as VerificationItem[];
}

export async function setVerification(
  tenantId: string,
  body: {
    practitioner_id: string;
    status: "pending" | "approved" | "rejected";
    reason?: string | null;
  },
): Promise<void> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/verification`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status !== 200 && res.status !== 204) {
    throw new Error(detailMessage(res.json, "verification_failed"));
  }
}

export async function registerPractitioner(
  tenantId: string,
  body: { display_name: string; user_id?: string | null },
): Promise<{ id: string }> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/practitioners`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "practitioner_failed"));
  }
  return res.json as { id: string };
}

export async function listStaffSchedules(
  tenantId: string,
  opts: { membershipId?: string; locationId?: string } = {},
): Promise<StaffSchedule[]> {
  const params = new URLSearchParams();
  if (opts.membershipId) params.set("membership_id", opts.membershipId);
  if (opts.locationId) params.set("location_id", opts.locationId);
  const q = params.toString();
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/staff-schedules${q ? `?${q}` : ""}`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as StaffSchedule[];
}

export async function createStaffSchedule(
  tenantId: string,
  body: {
    membership_id: string;
    location_id: string;
    weekday: number;
    start_time: string;
    end_time: string;
    break_minutes?: number;
    effective_from: string;
    effective_to?: string | null;
  },
): Promise<StaffSchedule> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/staff-schedules`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "schedule_failed"));
  }
  return res.json as StaffSchedule;
}

export async function deactivateStaffSchedule(
  tenantId: string,
  scheduleId: string,
): Promise<void> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/staff-schedules/${scheduleId}/deactivate`,
    tenantId,
    { method: "POST", body: {} },
  );
  if (res.status !== 200 && res.status !== 204) {
    throw new Error(detailMessage(res.json, "deactivate_failed"));
  }
}

export async function attendanceCheckIn(
  tenantId: string,
  locationId: string,
): Promise<Attendance> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/attendance/check-in`,
    tenantId,
    { method: "POST", body: { location_id: locationId } },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "checkin_failed"));
  }
  return res.json as Attendance;
}

export async function attendanceCheckOut(
  tenantId: string,
  attendanceId?: string | null,
): Promise<Attendance> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/attendance/check-out`,
    tenantId,
    {
      method: "POST",
      body: { attendance_id: attendanceId ?? null },
    },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "checkout_failed"));
  return res.json as Attendance;
}

export async function listAttendance(
  tenantId: string,
  opts: {
    membershipId?: string;
    locationId?: string;
    fromDate?: string;
    toDate?: string;
  } = {},
): Promise<Attendance[]> {
  const params = new URLSearchParams();
  if (opts.membershipId) params.set("membership_id", opts.membershipId);
  if (opts.locationId) params.set("location_id", opts.locationId);
  if (opts.fromDate) params.set("from_date", opts.fromDate);
  if (opts.toDate) params.set("to_date", opts.toDate);
  const q = params.toString();
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/attendance${q ? `?${q}` : ""}`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as Attendance[];
}

export async function correctAttendance(
  tenantId: string,
  attendanceId: string,
  body: {
    check_in_at?: string | null;
    check_out_at?: string | null;
    reason: string;
  },
): Promise<Attendance> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/attendance/${attendanceId}/correct`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "correct_failed"));
  return res.json as Attendance;
}

export async function listLeaveTypes(tenantId: string): Promise<LeaveType[]> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/leave-types`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return (res.json as LeaveType[]).filter((t) => t.is_active !== false);
}

export async function listLeaveRequests(
  tenantId: string,
  opts: { membershipId?: string; status?: string } = {},
): Promise<LeaveRequest[]> {
  const params = new URLSearchParams();
  if (opts.membershipId) params.set("membership_id", opts.membershipId);
  if (opts.status) params.set("status", opts.status);
  const q = params.toString();
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/leave-requests${q ? `?${q}` : ""}`,
    tenantId,
  );
  if (res.status !== 200 || !Array.isArray(res.json)) return [];
  return res.json as LeaveRequest[];
}

export async function createLeaveRequest(
  tenantId: string,
  body: {
    leave_type_id: string;
    start_date: string;
    end_date: string;
    reason?: string | null;
  },
): Promise<LeaveRequest> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/leave-requests`,
    tenantId,
    { method: "POST", body },
  );
  if (res.status !== 200 && res.status !== 201) {
    throw new Error(detailMessage(res.json, "leave_failed"));
  }
  return res.json as LeaveRequest;
}

export async function decideLeaveRequest(
  tenantId: string,
  leaveId: string,
  decision: "approved" | "rejected",
  note?: string | null,
): Promise<LeaveRequest> {
  const res = await staffFetch(
    `/api/v1/tenants/${tenantId}/leave-requests/${leaveId}/decide`,
    tenantId,
    { method: "POST", body: { decision, note: note ?? null } },
  );
  if (res.status !== 200) throw new Error(detailMessage(res.json, "decide_failed"));
  return res.json as LeaveRequest;
}
