import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  LoadingState,
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
import { fetchTenantLocations } from "../../lib/api";
import { fmtDate, fmtTime, fmtWhen, statusLabel, toDateInput } from "../../lib/format";
import { hasPerm } from "../../lib/nav";
import { useSession } from "../../lib/session";
import {
  WEEKDAY_LABELS,
  attendanceCheckIn,
  attendanceCheckOut,
  correctAttendance,
  createInvitation,
  createLeaveRequest,
  createStaffSchedule,
  deactivateStaffSchedule,
  decideLeaveRequest,
  getStaff,
  listAttendance,
  listInvitations,
  listLeaveRequests,
  listLeaveTypes,
  listPractitionersStatus,
  listRoles,
  listStaff,
  listStaffSchedules,
  listVerificationQueue,
  registerPractitioner,
  revokeInvitation,
  setVerification,
  updateStaff,
  type Attendance,
  type Invitation,
  type LeaveRequest,
  type LeaveType,
  type PractitionerStatus,
  type Role,
  type StaffMember,
  type StaffSchedule,
  type VerificationItem,
} from "../../lib/staffApi";

type HubTab =
  | "overview"
  | "directory"
  | "invitations"
  | "practitioners"
  | "schedules"
  | "attendance"
  | "leave";

type Location = { id: string; name: string };

type OverviewSlice<T> = {
  data: T;
  loaded: boolean;
  forbidden: boolean;
};

const ACTIVE_FILTERS = [
  { value: "active", label: "Active only" },
  { value: "inactive", label: "Inactive only" },
  { value: "all", label: "All" },
];

const EMPLOYMENT_OPTIONS = [
  { value: "active", label: "Active" },
  { value: "on_leave", label: "On leave" },
  { value: "terminated", label: "Terminated" },
];

const LEAVE_STATUS_FILTERS = [
  { value: "", label: "All statuses" },
  { value: "pending", label: "Pending" },
  { value: "approved", label: "Approved" },
  { value: "rejected", label: "Rejected" },
];

function todayWeekdayIndex(): number {
  const d = new Date().getDay();
  return d === 0 ? 6 : d - 1;
}

function handleApiError(
  e: unknown,
  onSessionExpired: () => void,
  setError: (msg: string) => void,
  fallback: string,
) {
  const msg = String(e);
  if (msg.includes("session_expired")) onSessionExpired();
  else if (msg.includes("forbidden"))
    setError("You do not have permission for this action.");
  else setError(msg.replace(/^Error:\s*/, "") || fallback);
}

function softLoad<T>(
  fn: () => Promise<T>,
  onSessionExpired: () => void,
): Promise<OverviewSlice<T>> {
  return fn()
    .then((data) => ({ data, loaded: true, forbidden: false }))
    .catch((e) => {
      if (String(e).includes("session_expired")) {
        onSessionExpired();
        return { data: [] as T, loaded: false, forbidden: false };
      }
      if (String(e).includes("forbidden")) {
        return { data: [] as T, loaded: true, forbidden: true };
      }
      return { data: [] as T, loaded: true, forbidden: false };
    });
}

function inviteOnlyCaption(inviteOnly: boolean, canManage: boolean): string | null {
  if (inviteOnly && !canManage) {
    return "Invite-only access: staff directory and HR edits require staff.manage.";
  }
  return null;
}

export function StaffHub({ onSessionExpired }: { onSessionExpired: () => void }) {
  const { tenant, workspace } = useSession();
  const perms = workspace?.permissions;

  const canManage = hasPerm(perms, "staff.manage");
  const canInvite = hasPerm(perms, "staff.invite");
  const canTenantRead = hasPerm(perms, "tenant.read");
  const canApptRead = hasPerm(perms, "appointment.read");
  const canSeePractitioners = canApptRead || canManage;
  const inviteOnly = canInvite && !canManage;

  const visibleTabs = useMemo((): HubTab[] => {
    const tabs: HubTab[] = ["overview"];
    if (canManage) tabs.push("directory");
    if (canInvite) tabs.push("invitations");
    if (canSeePractitioners) tabs.push("practitioners");
    if (canManage) {
      tabs.push("schedules", "attendance", "leave");
    } else if (canTenantRead) {
      tabs.push("attendance", "leave");
    }
    return tabs;
  }, [canManage, canInvite, canSeePractitioners, canTenantRead]);

  const [tab, setTab] = useState<HubTab>(inviteOnly ? "invitations" : "overview");
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [locations, setLocations] = useState<Location[]>([]);
  const [roles, setRoles] = useState<Role[]>([]);

  const [staffRows, setStaffRows] = useState<StaffMember[]>([]);
  const [staffLoading, setStaffLoading] = useState(false);
  const [staffForbidden, setStaffForbidden] = useState(false);
  const [dirQ, setDirQ] = useState("");
  const [dirActive, setDirActive] = useState("active");
  const [dirLocation, setDirLocation] = useState("");

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [profile, setProfile] = useState<StaffMember | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [editDesignation, setEditDesignation] = useState("");
  const [editPhone, setEditPhone] = useState("");
  const [editEmployment, setEditEmployment] = useState("active");
  const [editRole, setEditRole] = useState("");
  const [editActive, setEditActive] = useState(true);
  const [roleConfirmOpen, setRoleConfirmOpen] = useState(false);
  const [pendingRole, setPendingRole] = useState<string | null>(null);

  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [invLoading, setInvLoading] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("receptionist");
  const [inviteTtl, setInviteTtl] = useState("7");
  const [inviteTokenOnce, setInviteTokenOnce] = useState<{
    email: string;
    token: string;
    expires_at: string;
  } | null>(null);
  const [revokeTarget, setRevokeTarget] = useState<Invitation | null>(null);
  const [revokeOpen, setRevokeOpen] = useState(false);

  const [practitioners, setPractitioners] = useState<PractitionerStatus[]>([]);
  const [verificationQueue, setVerificationQueue] = useState<VerificationItem[]>([]);
  const [practLoading, setPractLoading] = useState(false);
  const [regName, setRegName] = useState("");
  const [regUserId, setRegUserId] = useState("");
  const [rejectReason, setRejectReason] = useState("");
  const [rejectTarget, setRejectTarget] = useState<VerificationItem | null>(null);
  const [rejectOpen, setRejectOpen] = useState(false);

  const [schedules, setSchedules] = useState<StaffSchedule[]>([]);
  const [schedLoading, setSchedLoading] = useState(false);
  const [schedMember, setSchedMember] = useState("");
  const [schedLocation, setSchedLocation] = useState("");
  const [schedWeekday, setSchedWeekday] = useState("0");
  const [schedStart, setSchedStart] = useState("09:00");
  const [schedEnd, setSchedEnd] = useState("17:00");
  const [schedFrom, setSchedFrom] = useState(toDateInput(new Date()));
  const [deactSchedId, setDeactSchedId] = useState<string | null>(null);
  const [deactSchedOpen, setDeactSchedOpen] = useState(false);

  const [attendanceRows, setAttendanceRows] = useState<Attendance[]>([]);
  const [attLoading, setAttLoading] = useState(false);
  const [attLocation, setAttLocation] = useState("");
  const [attMember, setAttMember] = useState("");
  const [attFrom, setAttFrom] = useState("");
  const [attTo, setAttTo] = useState("");
  const [correctRow, setCorrectRow] = useState<Attendance | null>(null);
  const [correctIn, setCorrectIn] = useState("");
  const [correctOut, setCorrectOut] = useState("");
  const [correctReason, setCorrectReason] = useState("");

  const [leaveTypes, setLeaveTypes] = useState<LeaveType[]>([]);
  const [leaveRows, setLeaveRows] = useState<LeaveRequest[]>([]);
  const [leaveLoading, setLeaveLoading] = useState(false);
  const [leaveTypeId, setLeaveTypeId] = useState("");
  const [leaveStart, setLeaveStart] = useState("");
  const [leaveEnd, setLeaveEnd] = useState("");
  const [leaveReason, setLeaveReason] = useState("");
  const [leaveStatusFilter, setLeaveStatusFilter] = useState("");
  const [leaveDecideTarget, setLeaveDecideTarget] = useState<{
    row: LeaveRequest;
    decision: "approved" | "rejected";
  } | null>(null);
  const [leaveDecideOpen, setLeaveDecideOpen] = useState(false);
  const [leaveDecideNote, setLeaveDecideNote] = useState("");

  const [overviewStaff, setOverviewStaff] = useState<OverviewSlice<StaffMember[]>>({
    data: [],
    loaded: false,
    forbidden: false,
  });
  const [overviewInvites, setOverviewInvites] = useState<OverviewSlice<Invitation[]>>({
    data: [],
    loaded: false,
    forbidden: false,
  });
  const [overviewVerification, setOverviewVerification] = useState<
    OverviewSlice<VerificationItem[]>
  >({ data: [], loaded: false, forbidden: false });
  const [overviewLeave, setOverviewLeave] = useState<OverviewSlice<LeaveRequest[]>>({
    data: [],
    loaded: false,
    forbidden: false,
  });
  const [overviewSchedules, setOverviewSchedules] = useState<OverviewSlice<StaffSchedule[]>>({
    data: [],
    loaded: false,
    forbidden: false,
  });

  const roleOptions = useMemo(() => {
    if (roles.length > 0) {
      return roles.map((r) => ({ value: r.name, label: r.name }));
    }
    const seen = new Set<string>();
    for (const s of staffRows) seen.add(s.role);
    return [...seen].map((name) => ({ value: name, label: name }));
  }, [roles, staffRows]);

  const locationOptions = useMemo(
    () => [
      { value: "", label: "All locations" },
      ...locations.map((l) => ({ value: l.id, label: l.name })),
    ],
    [locations],
  );

  const staffSelectOptions = useMemo(
    () =>
      staffRows.map((s) => ({
        value: s.membership_id,
        label: s.display_name,
      })),
    [staffRows],
  );

  const userIdOptions = useMemo(
    () => [
      { value: "", label: "No linked user" },
      ...staffRows.map((s) => ({
        value: s.user_id,
        label: `${s.display_name} (${s.email})`,
      })),
    ],
    [staffRows],
  );

  const weekdayOptions = useMemo(
    () =>
      WEEKDAY_LABELS.map((label, i) => ({
        value: String(i),
        label,
      })),
    [],
  );

  const loadLocationsAndRoles = useCallback(async () => {
    if (!tenant) return;
    try {
      const locs = await fetchTenantLocations(tenant.id);
      setLocations(locs);
      if (!schedLocation && locs[0]) setSchedLocation(locs[0].id);
      if (!attLocation && locs[0]) setAttLocation(locs[0].id);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Could not load locations.");
    }
    if (canTenantRead) {
      try {
        const r = await listRoles(tenant.id);
        setRoles(r);
        if (r.length && !r.some((x) => x.name === inviteRole)) {
          setInviteRole(r[0]!.name);
        }
      } catch (e) {
        if (!String(e).includes("forbidden")) {
          handleApiError(e, onSessionExpired, setError, "Could not load roles.");
        }
      }
    }
  }, [tenant, canTenantRead, onSessionExpired, schedLocation, attLocation, inviteRole]);

  const reloadStaffDirectory = useCallback(async () => {
    if (!tenant || !canManage) return;
    setStaffLoading(true);
    setStaffForbidden(false);
    try {
      const data = await listStaff(tenant.id, {
        q: dirQ.trim() || undefined,
        activeOnly: dirActive === "active",
        locationId: dirLocation || undefined,
      });
      let rows = data;
      if (dirActive === "inactive") rows = data.filter((s) => !s.is_active);
      setStaffRows(rows);
    } catch (e) {
      if (String(e).includes("forbidden")) setStaffForbidden(true);
      else handleApiError(e, onSessionExpired, setError, "Failed to load staff.");
    } finally {
      setStaffLoading(false);
    }
  }, [tenant, canManage, dirQ, dirActive, dirLocation, onSessionExpired]);

  const reloadOverview = useCallback(async () => {
    if (!tenant) return;
    const tid = tenant.id;
    if (canManage) {
      setOverviewStaff(await softLoad(() => listStaff(tid, { activeOnly: false }), onSessionExpired));
      setOverviewVerification(
        await softLoad(() => listVerificationQueue(tid), onSessionExpired),
      );
      setOverviewSchedules(await softLoad(() => listStaffSchedules(tid), onSessionExpired));
      setOverviewLeave(
        await softLoad(() => listLeaveRequests(tid, { status: "pending" }), onSessionExpired),
      );
    }
    if (canInvite) {
      setOverviewInvites(
        await softLoad(() => listInvitations(tid, "pending"), onSessionExpired),
      );
    }
  }, [tenant, canManage, canInvite, onSessionExpired]);

  const reloadInvitations = useCallback(async () => {
    if (!tenant || !canInvite) return;
    setInvLoading(true);
    try {
      const rows = await listInvitations(tenant.id);
      setInvitations(rows);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Failed to load invitations.");
    } finally {
      setInvLoading(false);
    }
  }, [tenant, canInvite, onSessionExpired]);

  const reloadPractitioners = useCallback(async () => {
    if (!tenant || !canSeePractitioners) return;
    setPractLoading(true);
    try {
      const [plist, queue] = await Promise.all([
        listPractitionersStatus(tenant.id),
        canManage ? listVerificationQueue(tenant.id) : Promise.resolve([]),
      ]);
      setPractitioners(plist);
      setVerificationQueue(queue);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Failed to load practitioners.");
    } finally {
      setPractLoading(false);
    }
  }, [tenant, canSeePractitioners, canManage, onSessionExpired]);

  const reloadSchedules = useCallback(async () => {
    if (!tenant || !canManage) return;
    setSchedLoading(true);
    try {
      const rows = await listStaffSchedules(tenant.id);
      setSchedules(rows);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Failed to load schedules.");
    } finally {
      setSchedLoading(false);
    }
  }, [tenant, canManage, onSessionExpired]);

  const reloadAttendance = useCallback(async () => {
    if (!tenant || !canTenantRead) return;
    setAttLoading(true);
    try {
      const rows = await listAttendance(tenant.id, {
        membershipId: canManage && attMember ? attMember : undefined,
        locationId: attLocation || undefined,
        fromDate: attFrom || undefined,
        toDate: attTo || undefined,
      });
      setAttendanceRows(rows);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Failed to load attendance.");
    } finally {
      setAttLoading(false);
    }
  }, [tenant, canTenantRead, canManage, attMember, attLocation, attFrom, attTo, onSessionExpired]);

  const reloadLeave = useCallback(async () => {
    if (!tenant || !canTenantRead) return;
    setLeaveLoading(true);
    try {
      const [types, requests] = await Promise.all([
        listLeaveTypes(tenant.id),
        listLeaveRequests(tenant.id, {
          status: leaveStatusFilter || undefined,
        }),
      ]);
      setLeaveTypes(types);
      setLeaveRows(requests);
      if (!leaveTypeId && types[0]) setLeaveTypeId(types[0].id);
    } catch (e) {
      handleApiError(e, onSessionExpired, setError, "Failed to load leave.");
    } finally {
      setLeaveLoading(false);
    }
  }, [tenant, canTenantRead, leaveStatusFilter, leaveTypeId, onSessionExpired]);

  useEffect(() => {
    void loadLocationsAndRoles();
  }, [loadLocationsAndRoles]);

  useEffect(() => {
    void reloadOverview();
  }, [reloadOverview]);

  useEffect(() => {
    if (tab === "directory") void reloadStaffDirectory();
  }, [tab, reloadStaffDirectory]);

  useEffect(() => {
    if (tab === "invitations") void reloadInvitations();
  }, [tab, reloadInvitations]);

  useEffect(() => {
    if (tab === "practitioners") void reloadPractitioners();
  }, [tab, reloadPractitioners]);

  useEffect(() => {
    if (tab === "schedules") void reloadSchedules();
  }, [tab, reloadSchedules]);

  useEffect(() => {
    if (!tenant || !canManage) return;
    if (
      tab === "schedules" ||
      tab === "attendance" ||
      tab === "practitioners" ||
      tab === "leave"
    ) {
      void listStaff(tenant.id, { activeOnly: false })
        .then(setStaffRows)
        .catch((e) => {
          if (String(e).includes("session_expired")) onSessionExpired();
        });
    }
  }, [tab, tenant, canManage, onSessionExpired]);

  useEffect(() => {
    if (tab === "attendance") void reloadAttendance();
  }, [tab, reloadAttendance]);

  useEffect(() => {
    if (tab === "leave") void reloadLeave();
  }, [tab, reloadLeave]);

  useEffect(() => {
    if (tab !== "directory") {
      setSelectedId(null);
      setProfile(null);
    }
  }, [tab]);

  useEffect(() => {
    if (!tenant || !selectedId || !canManage) return;
    let cancelled = false;
    (async () => {
      setProfileLoading(true);
      try {
        const row = await getStaff(tenant.id, selectedId);
        if (cancelled) return;
        setProfile(row);
        setEditDesignation(row.designation ?? "");
        setEditPhone(row.phone ?? "");
        setEditEmployment(row.employment_status);
        setEditRole(row.role);
        setEditActive(row.is_active);
      } catch (e) {
        if (cancelled) return;
        handleApiError(e, onSessionExpired, setError, "Could not load staff profile.");
        setProfile(null);
      } finally {
        if (!cancelled) setProfileLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [tenant, selectedId, canManage, onSessionExpired]);

  useEffect(() => {
    if (staffRows.length && !schedMember) {
      setSchedMember(staffRows[0]!.membership_id);
    }
  }, [staffRows, schedMember]);

  const overviewMetrics = useMemo(() => {
    const activeStaff = overviewStaff.loaded
      ? overviewStaff.data.filter((s) => s.is_active).length
      : null;
    const pendingInvites = overviewInvites.loaded
      ? overviewInvites.data.filter((i) => i.status === "pending").length
      : null;
    const pendingVerification = overviewVerification.loaded
      ? overviewVerification.data.filter((v) => v.status === "pending").length
      : null;
    const pendingLeave = overviewLeave.loaded ? overviewLeave.data.length : null;
    const todayIdx = todayWeekdayIndex();
    const todaySchedules =
      overviewSchedules.loaded && !overviewSchedules.forbidden
        ? overviewSchedules.data.filter((s) => s.is_active && s.weekday === todayIdx).length
        : null;
    return {
      activeStaff,
      pendingInvites,
      pendingVerification,
      pendingLeave,
      todaySchedules,
    };
  }, [overviewStaff, overviewInvites, overviewVerification, overviewLeave, overviewSchedules]);

  async function onSaveProfile(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !profile || !canManage) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    try {
      const updated = await updateStaff(tenant.id, profile.membership_id, {
        designation: editDesignation.trim() || null,
        phone: editPhone.trim() || null,
        employment_status: editEmployment,
        is_active: editActive,
      });
      setProfile(updated);
      setInfo("Staff profile updated.");
      void reloadStaffDirectory();
      void reloadOverview();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Profile update failed.");
    } finally {
      setBusy(false);
    }
  }

  function onRoleSelectChange(next: string) {
    if (!profile || next === profile.role) {
      setEditRole(next);
      return;
    }
    setPendingRole(next);
    setRoleConfirmOpen(true);
  }

  async function confirmRoleChange() {
    if (!tenant || !profile || !pendingRole) return;
    setBusy(true);
    setError(null);
    try {
      const updated = await updateStaff(tenant.id, profile.membership_id, {
        role: pendingRole,
      });
      setProfile(updated);
      setEditRole(updated.role);
      setInfo(`Role updated to ${pendingRole}.`);
      void reloadStaffDirectory();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Role change failed.");
    } finally {
      setBusy(false);
      setRoleConfirmOpen(false);
      setPendingRole(null);
    }
  }

  async function onCreateInvite(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !canInvite) return;
    setBusy(true);
    setError(null);
    setInfo(null);
    setInviteTokenOnce(null);
    try {
      const ttl = Number(inviteTtl);
      const created = await createInvitation(tenant.id, {
        email: inviteEmail.trim(),
        role: inviteRole,
        ttl_days: Number.isFinite(ttl) && ttl > 0 ? ttl : undefined,
      });
      setInviteTokenOnce({
        email: created.email,
        token: created.token,
        expires_at: created.expires_at,
      });
      setInfo(`Invitation created for ${created.email}. Copy the token below — it is shown once.`);
      setInviteEmail("");
      void reloadInvitations();
      void reloadOverview();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Invitation failed.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmRevokeInvite() {
    if (!tenant || !revokeTarget) return;
    setBusy(true);
    setError(null);
    try {
      await revokeInvitation(tenant.id, revokeTarget.id);
      setInfo("Invitation revoked.");
      void reloadInvitations();
      void reloadOverview();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Revoke failed.");
    } finally {
      setBusy(false);
      setRevokeOpen(false);
      setRevokeTarget(null);
    }
  }

  async function copyInviteToken() {
    if (!inviteTokenOnce) return;
    try {
      await navigator.clipboard.writeText(inviteTokenOnce.token);
      setInfo("Invite token copied. Share it securely with the invitee.");
    } catch {
      setError("Could not copy token to clipboard.");
    }
  }

  function dismissInviteToken() {
    setInviteTokenOnce(null);
  }

  async function onRegisterPractitioner(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !canManage) return;
    if (regName.trim().length < 2) {
      setError("Display name must be at least 2 characters.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await registerPractitioner(tenant.id, {
        display_name: regName.trim(),
        user_id: regUserId || null,
      });
      setRegName("");
      setRegUserId("");
      setInfo("Practitioner registered.");
      void reloadPractitioners();
      void reloadOverview();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Registration failed.");
    } finally {
      setBusy(false);
    }
  }

  async function approveVerification(item: VerificationItem) {
    if (!tenant || !canManage) return;
    setBusy(true);
    setError(null);
    try {
      await setVerification(tenant.id, {
        practitioner_id: item.practitioner_id,
        status: "approved",
      });
      setInfo(`Approved ${item.display_name}.`);
      void reloadPractitioners();
      void reloadOverview();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Approval failed.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmRejectVerification() {
    if (!tenant || !rejectTarget) return;
    setBusy(true);
    setError(null);
    try {
      await setVerification(tenant.id, {
        practitioner_id: rejectTarget.practitioner_id,
        status: "rejected",
        reason: rejectReason.trim() || null,
      });
      setInfo("Verification rejected.");
      setRejectReason("");
      void reloadPractitioners();
      void reloadOverview();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Rejection failed.");
    } finally {
      setBusy(false);
      setRejectOpen(false);
      setRejectTarget(null);
    }
  }

  async function onCreateSchedule(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !canManage) return;
    if (!schedMember || !schedLocation) {
      setError("Select staff and location.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createStaffSchedule(tenant.id, {
        membership_id: schedMember,
        location_id: schedLocation,
        weekday: Number(schedWeekday),
        start_time: schedStart.length === 5 ? `${schedStart}:00` : schedStart,
        end_time: schedEnd.length === 5 ? `${schedEnd}:00` : schedEnd,
        effective_from: schedFrom,
      });
      setInfo("Schedule created.");
      void reloadSchedules();
      void reloadOverview();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Schedule create failed.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmDeactivateSchedule() {
    if (!tenant || !deactSchedId) return;
    setBusy(true);
    setError(null);
    try {
      await deactivateStaffSchedule(tenant.id, deactSchedId);
      setInfo("Schedule deactivated.");
      void reloadSchedules();
      void reloadOverview();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Deactivate failed.");
    } finally {
      setBusy(false);
      setDeactSchedOpen(false);
      setDeactSchedId(null);
    }
  }

  async function onCheckIn() {
    if (!tenant || !attLocation) {
      setError("Select a location to check in.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await attendanceCheckIn(tenant.id, attLocation);
      setInfo("Checked in.");
      void reloadAttendance();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Check-in failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onCheckOut() {
    if (!tenant) return;
    setBusy(true);
    setError(null);
    try {
      await attendanceCheckOut(tenant.id);
      setInfo("Checked out.");
      void reloadAttendance();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Check-out failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onCorrectAttendance(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !correctRow || !canManage) return;
    if (!correctReason.trim()) {
      setError("Correction reason is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await correctAttendance(tenant.id, correctRow.id, {
        check_in_at: correctIn || null,
        check_out_at: correctOut || null,
        reason: correctReason.trim(),
      });
      setInfo("Attendance corrected.");
      setCorrectRow(null);
      setCorrectReason("");
      void reloadAttendance();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Correction failed.");
    } finally {
      setBusy(false);
    }
  }

  async function onCreateLeave(e: FormEvent) {
    e.preventDefault();
    if (!tenant || !canTenantRead) return;
    setBusy(true);
    setError(null);
    try {
      await createLeaveRequest(tenant.id, {
        leave_type_id: leaveTypeId,
        start_date: leaveStart,
        end_date: leaveEnd,
        reason: leaveReason.trim() || null,
      });
      setInfo("Leave request submitted.");
      setLeaveStart("");
      setLeaveEnd("");
      setLeaveReason("");
      void reloadLeave();
      void reloadOverview();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Leave request failed.");
    } finally {
      setBusy(false);
    }
  }

  async function confirmLeaveDecision() {
    if (!tenant || !leaveDecideTarget) return;
    setBusy(true);
    setError(null);
    try {
      await decideLeaveRequest(
        tenant.id,
        leaveDecideTarget.row.id,
        leaveDecideTarget.decision,
        leaveDecideNote.trim() || null,
      );
      setInfo(`Leave ${leaveDecideTarget.decision}.`);
      setLeaveDecideNote("");
      void reloadLeave();
      void reloadOverview();
    } catch (err) {
      handleApiError(err, onSessionExpired, setError, "Decision failed.");
    } finally {
      setBusy(false);
      setLeaveDecideOpen(false);
      setLeaveDecideTarget(null);
    }
  }

  const inviteCaption = inviteOnlyCaption(inviteOnly, canManage);

  if (!tenant) {
    return <LoadingState label="Select a clinic workspace" />;
  }

  return (
    <div className="hos-staff">
      <header className="hos-module-header">
        <h1>Staff & workforce</h1>
        <p className="hos-muted">Directory, invitations, practitioners, schedules, attendance, leave</p>
      </header>

      {inviteCaption && (
        <Alert tone="warning" title="Limited access">
          {inviteCaption}
        </Alert>
      )}

      {error && (
        <Alert tone="danger" title="Staff">
          {error}
        </Alert>
      )}
      {info && (
        <Alert tone="success" title="Updated">
          {info}
        </Alert>
      )}

      <Tabs
        value={tab}
        onValueChange={(v) => {
          if (visibleTabs.includes(v as HubTab)) setTab(v as HubTab);
        }}
      >
        <TabsList>
          {visibleTabs.includes("overview") && (
            <TabsTrigger value="overview">Overview</TabsTrigger>
          )}
          {visibleTabs.includes("directory") && (
            <TabsTrigger value="directory">Directory</TabsTrigger>
          )}
          {visibleTabs.includes("invitations") && (
            <TabsTrigger value="invitations">Invitations</TabsTrigger>
          )}
          {visibleTabs.includes("practitioners") && (
            <TabsTrigger value="practitioners">Practitioners</TabsTrigger>
          )}
          {visibleTabs.includes("schedules") && (
            <TabsTrigger value="schedules">Schedules</TabsTrigger>
          )}
          {visibleTabs.includes("attendance") && (
            <TabsTrigger value="attendance">Attendance</TabsTrigger>
          )}
          {visibleTabs.includes("leave") && (
            <TabsTrigger value="leave">Leave</TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="overview">
          <p className="hos-caption">
            Counts come from data your role can load. Invite-only roles cannot load the staff directory.
          </p>
          <div className="hos-dash-grid">
            <Card title="Active staff">
              {overviewStaff.forbidden ? (
                <p className="hos-muted">Directory not available for your role.</p>
              ) : overviewStaff.loaded ? (
                <p className="hos-metric-value">{overviewMetrics.activeStaff ?? "—"}</p>
              ) : (
                <LoadingState label="Loading" />
              )}
            </Card>
            <Card title="Pending invitations">
              {overviewInvites.forbidden ? (
                <p className="hos-muted">Not available.</p>
              ) : overviewInvites.loaded ? (
                <p className="hos-metric-value">{overviewMetrics.pendingInvites ?? "—"}</p>
              ) : canInvite ? (
                <LoadingState label="Loading" />
              ) : (
                <p className="hos-muted">Requires staff.invite.</p>
              )}
            </Card>
            <Card title="Pending verifications">
              {overviewVerification.forbidden ? (
                <p className="hos-muted">Not available.</p>
              ) : overviewVerification.loaded ? (
                <p className="hos-metric-value">{overviewMetrics.pendingVerification ?? "—"}</p>
              ) : canManage ? (
                <LoadingState label="Loading" />
              ) : (
                <p className="hos-muted">Requires staff.manage.</p>
              )}
            </Card>
            <Card title="Pending leave">
              {overviewLeave.forbidden ? (
                <p className="hos-muted">Not available.</p>
              ) : overviewLeave.loaded ? (
                <p className="hos-metric-value">{overviewMetrics.pendingLeave ?? "—"}</p>
              ) : canManage ? (
                <LoadingState label="Loading" />
              ) : (
                <p className="hos-muted">—</p>
              )}
            </Card>
            <Card title="Today's schedules">
              {overviewSchedules.forbidden ? (
                <p className="hos-muted">Not available.</p>
              ) : overviewSchedules.loaded ? (
                <p className="hos-metric-value">{overviewMetrics.todaySchedules ?? "—"}</p>
              ) : canManage ? (
                <LoadingState label="Loading" />
              ) : (
                <p className="hos-muted">Requires staff.manage.</p>
              )}
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="directory">
          <div className="hos-toolbar-row">
            <Field label="Search" htmlFor="staff-q">
              {({ describedBy }) => (
                <Input
                  id="staff-q"
                  aria-describedby={describedBy}
                  value={dirQ}
                  onChange={(ev) => setDirQ(ev.target.value)}
                  placeholder="Name or email"
                />
              )}
            </Field>
            <Field label="Status" htmlFor="staff-active">
              {({ describedBy }) => (
                <Select
                  id="staff-active"
                  aria-describedby={describedBy}
                  value={dirActive}
                  onChange={(ev) => setDirActive(ev.target.value)}
                  options={ACTIVE_FILTERS}
                />
              )}
            </Field>
            <Field label="Location" htmlFor="staff-loc-dir">
              {({ describedBy }) => (
                <Select
                  id="staff-loc-dir"
                  aria-describedby={describedBy}
                  value={dirLocation}
                  onChange={(ev) => setDirLocation(ev.target.value)}
                  options={locationOptions}
                />
              )}
            </Field>
            <Button type="button" onClick={() => void reloadStaffDirectory()}>
              Apply
            </Button>
          </div>

          {staffForbidden ? (
            <Alert tone="warning" title="Directory">
              Staff directory requires staff.manage.
            </Alert>
          ) : (
            <div className="hos-staff-layout">
              <Card title="Staff directory">
                {staffLoading && staffRows.length === 0 ? (
                  <LoadingState label="Loading staff" />
                ) : staffRows.length === 0 ? (
                  <EmptyState title="No staff found">Adjust filters or search.</EmptyState>
                ) : (
                  <Table
                    columns={
                      <>
                        <Th>Name</Th>
                        <Th>Email</Th>
                        <Th>Role</Th>
                        <Th>Designation</Th>
                        <Th>Status</Th>
                      </>
                    }
                  >
                    {staffRows.map((s) => (
                      <tr
                        key={s.membership_id}
                        className={
                          selectedId === s.membership_id ? "hos-row-selected" : undefined
                        }
                      >
                        <Td>
                          <button
                            type="button"
                            className="hos-link-btn"
                            onClick={() => setSelectedId(s.membership_id)}
                          >
                            {s.display_name}
                          </button>
                        </Td>
                        <Td>{s.email}</Td>
                        <Td>
                          <Badge tone="info">{s.role}</Badge>
                        </Td>
                        <Td>{s.designation ?? "—"}</Td>
                        <Td>
                          <Status value={s.is_active ? s.employment_status : "inactive"} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>

              <Card title="Profile">
                {profileLoading ? (
                  <LoadingState label="Loading profile" />
                ) : !profile ? (
                  <EmptyState title="No selection">Select a staff member from the table.</EmptyState>
                ) : (
                  <form onSubmit={onSaveProfile}>
                    <p>
                      <strong>{profile.display_name}</strong>
                      <br />
                      <span className="hos-muted">{profile.email}</span>
                    </p>
                    <Field label="Designation" htmlFor="prof-desig">
                      {({ describedBy }) => (
                        <Input
                          id="prof-desig"
                          aria-describedby={describedBy}
                          value={editDesignation}
                          onChange={(ev) => setEditDesignation(ev.target.value)}
                          disabled={!canManage}
                        />
                      )}
                    </Field>
                    <Field label="Phone" htmlFor="prof-phone">
                      {({ describedBy }) => (
                        <Input
                          id="prof-phone"
                          aria-describedby={describedBy}
                          value={editPhone}
                          onChange={(ev) => setEditPhone(ev.target.value)}
                          disabled={!canManage}
                        />
                      )}
                    </Field>
                    <Field label="Employment status" htmlFor="prof-emp">
                      {({ describedBy }) => (
                        <Select
                          id="prof-emp"
                          aria-describedby={describedBy}
                          value={editEmployment}
                          onChange={(ev) => setEditEmployment(ev.target.value)}
                          options={EMPLOYMENT_OPTIONS}
                          disabled={!canManage}
                        />
                      )}
                    </Field>
                    <Field label="Role" htmlFor="prof-role">
                      {({ describedBy }) => (
                        <Select
                          id="prof-role"
                          aria-describedby={describedBy}
                          value={editRole}
                          onChange={(ev) => onRoleSelectChange(ev.target.value)}
                          options={roleOptions}
                          disabled={!canManage || roleOptions.length === 0}
                        />
                      )}
                    </Field>
                    <Field label="Membership active" htmlFor="prof-active">
                      {({ describedBy }) => (
                        <Select
                          id="prof-active"
                          aria-describedby={describedBy}
                          value={editActive ? "true" : "false"}
                          onChange={(ev) => setEditActive(ev.target.value === "true")}
                          options={[
                            { value: "true", label: "Active" },
                            { value: "false", label: "Inactive" },
                          ]}
                          disabled={!canManage}
                        />
                      )}
                    </Field>
                    <p className="hos-caption">Joined {fmtDate(profile.joined_at)}</p>
                    {canManage && (
                      <Button type="submit" loading={busy} disabled={busy}>
                        Save profile
                      </Button>
                    )}
                  </form>
                )}
              </Card>
            </div>
          )}
        </TabsContent>

        <TabsContent value="invitations">
          {canInvite ? (
            <>
              <p className="hos-caption">
                Creating an invitation does not guarantee email delivery. Share the invite token
                manually on desktop — no automatic WhatsApp send.
              </p>
              <Card title="Invite staff">
                <form onSubmit={onCreateInvite}>
                  <Field label="Email" htmlFor="inv-email" required>
                    {({ describedBy }) => (
                      <Input
                        id="inv-email"
                        type="email"
                        aria-describedby={describedBy}
                        value={inviteEmail}
                        onChange={(ev) => setInviteEmail(ev.target.value)}
                        required
                      />
                    )}
                  </Field>
                  <Field label="Role" htmlFor="inv-role">
                    {({ describedBy }) => (
                      <Select
                        id="inv-role"
                        aria-describedby={describedBy}
                        value={inviteRole}
                        onChange={(ev) => setInviteRole(ev.target.value)}
                        options={
                          roleOptions.length > 0
                            ? roleOptions
                            : [{ value: "receptionist", label: "receptionist" }]
                        }
                      />
                    )}
                  </Field>
                  <Field
                    label="Expiry (days)"
                    htmlFor="inv-ttl"
                    description="Optional TTL passed to the server."
                  >
                    {({ describedBy }) => (
                      <Input
                        id="inv-ttl"
                        type="number"
                        min={1}
                        aria-describedby={describedBy}
                        value={inviteTtl}
                        onChange={(ev) => setInviteTtl(ev.target.value)}
                      />
                    )}
                  </Field>
                  <Button type="submit" loading={busy} disabled={busy}>
                    Create invitation
                  </Button>
                </form>

                {inviteTokenOnce && (
                  <Alert tone="warning" title="Invite token — copy now">
                    <p>
                      Token for <strong>{inviteTokenOnce.email}</strong> (shown once). Expires{" "}
                      {fmtWhen(inviteTokenOnce.expires_at)}.
                    </p>
                    <code className="hos-token-block">{inviteTokenOnce.token}</code>
                    <div className="hos-inline-actions">
                      <Button type="button" onClick={() => void copyInviteToken()}>
                        Copy token
                      </Button>
                      <Button type="button" variant="secondary" onClick={dismissInviteToken}>
                        Dismiss
                      </Button>
                    </div>
                  </Alert>
                )}
              </Card>

              <Card title="Pending invitations">
                {invLoading && invitations.length === 0 ? (
                  <LoadingState label="Loading invitations" />
                ) : invitations.filter((i) => i.status === "pending").length === 0 ? (
                  <EmptyState title="No pending invitations" />
                ) : (
                  <Table
                    columns={
                      <>
                        <Th>Email</Th>
                        <Th>Role</Th>
                        <Th>Expires</Th>
                        <Th>Actions</Th>
                      </>
                    }
                  >
                    {invitations
                      .filter((i) => i.status === "pending")
                      .map((i) => (
                        <tr key={i.id}>
                          <Td>{i.email}</Td>
                          <Td>{i.role}</Td>
                          <Td>{fmtWhen(i.expires_at)}</Td>
                          <Td>
                            <Button
                              type="button"
                              variant="danger"
                              onClick={() => {
                                setRevokeTarget(i);
                                setRevokeOpen(true);
                              }}
                            >
                              Revoke
                            </Button>
                          </Td>
                        </tr>
                      ))}
                  </Table>
                )}
              </Card>
            </>
          ) : (
            <Alert tone="warning" title="Invitations">Requires staff.invite.</Alert>
          )}
        </TabsContent>

        <TabsContent value="practitioners">
          <p className="hos-caption">
            Practitioner records are distinct from staff membership. Unapproved practitioners cannot
            be booked for appointments.
          </p>
          {canSeePractitioners ? (
            <>
              {canManage && (
                <Card title="Register practitioner">
                  <form onSubmit={onRegisterPractitioner}>
                    <Field label="Display name" htmlFor="pr-name" required>
                      {({ describedBy }) => (
                        <Input
                          id="pr-name"
                          aria-describedby={describedBy}
                          value={regName}
                          onChange={(ev) => setRegName(ev.target.value)}
                          required
                        />
                      )}
                    </Field>
                    <Field
                      label="Link staff user (optional)"
                      htmlFor="pr-user"
                      description="Optional user_id from staff directory."
                    >
                      {({ describedBy }) => (
                        <Select
                          id="pr-user"
                          aria-describedby={describedBy}
                          value={regUserId}
                          onChange={(ev) => setRegUserId(ev.target.value)}
                          options={userIdOptions}
                        />
                      )}
                    </Field>
                    <Button type="submit" loading={busy} disabled={busy}>
                      Register
                    </Button>
                  </form>
                </Card>
              )}

              <Card title="Practitioners">
                {practLoading && practitioners.length === 0 ? (
                  <LoadingState label="Loading practitioners" />
                ) : practitioners.length === 0 ? (
                  <EmptyState title="No practitioners" />
                ) : (
                  <Table
                    columns={
                      <>
                        <Th>Name</Th>
                        <Th>Verification</Th>
                      </>
                    }
                  >
                    {practitioners.map((p) => (
                      <tr key={p.id}>
                        <Td>{p.display_name}</Td>
                        <Td>
                          <Status value={p.verification_status} />
                        </Td>
                      </tr>
                    ))}
                  </Table>
                )}
              </Card>

              {canManage && (
                <Card title="Verification queue">
                  {verificationQueue.length === 0 ? (
                    <EmptyState title="Queue empty" />
                  ) : (
                    <Table
                      columns={
                        <>
                          <Th>Name</Th>
                          <Th>Status</Th>
                          <Th>Actions</Th>
                        </>
                      }
                    >
                      {verificationQueue.map((v) => (
                        <tr key={v.practitioner_id}>
                          <Td>{v.display_name}</Td>
                          <Td>
                            <Status value={v.status} />
                          </Td>
                          <Td>
                            <div className="hos-inline-actions">
                              <Button
                                type="button"
                                onClick={() => void approveVerification(v)}
                                disabled={busy || v.status !== "pending"}
                              >
                                Approve
                              </Button>
                              <Button
                                type="button"
                                variant="danger"
                                disabled={busy || v.status !== "pending"}
                                onClick={() => {
                                  setRejectTarget(v);
                                  setRejectOpen(true);
                                }}
                              >
                                Reject
                              </Button>
                            </div>
                          </Td>
                        </tr>
                      ))}
                    </Table>
                  )}
                </Card>
              )}
            </>
          ) : (
            <Alert tone="warning" title="Practitioners">
              Requires appointment.read or staff.manage.
            </Alert>
          )}
        </TabsContent>

        <TabsContent value="schedules">
          <p className="hos-caption">
            Staff schedules are HR working windows per membership — not appointment availability
            slots.
          </p>
          <Card title="Create schedule">
            <form onSubmit={onCreateSchedule}>
              <Field label="Staff" htmlFor="sch-member">
                {({ describedBy }) => (
                  <Select
                    id="sch-member"
                    aria-describedby={describedBy}
                    value={schedMember}
                    onChange={(ev) => setSchedMember(ev.target.value)}
                    options={
                      staffSelectOptions.length
                        ? staffSelectOptions
                        : [{ value: "", label: "Load directory first" }]
                    }
                  />
                )}
              </Field>
              <Field label="Location" htmlFor="sch-loc">
                {({ describedBy }) => (
                  <Select
                    id="sch-loc"
                    aria-describedby={describedBy}
                    value={schedLocation}
                    onChange={(ev) => setSchedLocation(ev.target.value)}
                    options={locationOptions.filter((o) => o.value !== "")}
                  />
                )}
              </Field>
              <Field label="Weekday" htmlFor="sch-day">
                {({ describedBy }) => (
                  <Select
                    id="sch-day"
                    aria-describedby={describedBy}
                    value={schedWeekday}
                    onChange={(ev) => setSchedWeekday(ev.target.value)}
                    options={weekdayOptions}
                  />
                )}
              </Field>
              <Field label="Start" htmlFor="sch-start">
                {({ describedBy }) => (
                  <Input
                    id="sch-start"
                    type="time"
                    aria-describedby={describedBy}
                    value={schedStart}
                    onChange={(ev) => setSchedStart(ev.target.value)}
                  />
                )}
              </Field>
              <Field label="End" htmlFor="sch-end">
                {({ describedBy }) => (
                  <Input
                    id="sch-end"
                    type="time"
                    aria-describedby={describedBy}
                    value={schedEnd}
                    onChange={(ev) => setSchedEnd(ev.target.value)}
                  />
                )}
              </Field>
              <Field label="Effective from" htmlFor="sch-from">
                {({ describedBy }) => (
                  <Input
                    id="sch-from"
                    type="date"
                    aria-describedby={describedBy}
                    value={schedFrom}
                    onChange={(ev) => setSchedFrom(ev.target.value)}
                    required
                  />
                )}
              </Field>
              <Button type="submit" loading={busy} disabled={busy}>
                Add schedule
              </Button>
            </form>
          </Card>

          <Card title="Schedules">
            {schedLoading && schedules.length === 0 ? (
              <LoadingState label="Loading schedules" />
            ) : schedules.length === 0 ? (
              <EmptyState title="No schedules" />
            ) : (
              <Table
                columns={
                  <>
                    <Th>Day</Th>
                    <Th>Hours</Th>
                    <Th>Break</Th>
                    <Th>Active</Th>
                    <Th>Actions</Th>
                  </>
                }
              >
                {schedules.map((s) => (
                  <tr key={s.id}>
                    <Td>{WEEKDAY_LABELS[s.weekday] ?? s.weekday}</Td>
                    <Td>
                      {s.start_time} – {s.end_time}
                    </Td>
                    <Td>{s.break_minutes}m</Td>
                    <Td>
                      <Status value={s.is_active ? "active" : "inactive"} />
                    </Td>
                    <Td>
                      {s.is_active ? (
                        <Button
                          type="button"
                          variant="secondary"
                          onClick={() => {
                            setDeactSchedId(s.id);
                            setDeactSchedOpen(true);
                          }}
                        >
                          Deactivate
                        </Button>
                      ) : (
                        "—"
                      )}
                    </Td>
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </TabsContent>

        <TabsContent value="attendance">
          <Card title="Self check-in / check-out">
            <p className="hos-caption">Requires tenant.read. Select your working location.</p>
            <div className="hos-toolbar-row">
              <Field label="Location" htmlFor="att-loc">
                {({ describedBy }) => (
                  <Select
                    id="att-loc"
                    aria-describedby={describedBy}
                    value={attLocation}
                    onChange={(ev) => setAttLocation(ev.target.value)}
                    options={locationOptions.filter((o) => o.value !== "")}
                  />
                )}
              </Field>
              <Button type="button" onClick={() => void onCheckIn()} loading={busy}>
                Check in
              </Button>
              <Button type="button" variant="secondary" onClick={() => void onCheckOut()} loading={busy}>
                Check out
              </Button>
            </div>
          </Card>

          <Card title="Attendance history">
            <div className="hos-toolbar-row">
              {canManage && (
                <Field label="Staff" htmlFor="att-member">
                  {({ describedBy }) => (
                    <Select
                      id="att-member"
                      aria-describedby={describedBy}
                      value={attMember}
                      onChange={(ev) => setAttMember(ev.target.value)}
                      options={[
                        { value: "", label: "All staff" },
                        ...staffSelectOptions,
                      ]}
                    />
                  )}
                </Field>
              )}
              <Field label="From" htmlFor="att-from">
                {({ describedBy }) => (
                  <Input
                    id="att-from"
                    type="date"
                    aria-describedby={describedBy}
                    value={attFrom}
                    onChange={(ev) => setAttFrom(ev.target.value)}
                  />
                )}
              </Field>
              <Field label="To" htmlFor="att-to">
                {({ describedBy }) => (
                  <Input
                    id="att-to"
                    type="date"
                    aria-describedby={describedBy}
                    value={attTo}
                    onChange={(ev) => setAttTo(ev.target.value)}
                  />
                )}
              </Field>
              <Button type="button" onClick={() => void reloadAttendance()}>
                Apply filters
              </Button>
            </div>

            {attLoading && attendanceRows.length === 0 ? (
              <LoadingState label="Loading attendance" />
            ) : attendanceRows.length === 0 ? (
              <EmptyState title="No records" />
            ) : (
              <Table
                columns={
                  <>
                    <Th>Date</Th>
                    <Th>In</Th>
                    <Th>Out</Th>
                    <Th>Duration</Th>
                    <Th>Source</Th>
                    {canManage ? <Th>Correct</Th> : null}
                  </>
                }
              >
                {attendanceRows.map((a) => (
                  <tr key={a.id}>
                    <Td>{a.attendance_date}</Td>
                    <Td>{fmtTime(a.check_in_at)}</Td>
                    <Td>{a.check_out_at ? fmtTime(a.check_out_at) : "—"}</Td>
                    <Td>{a.duration_minutes != null ? `${a.duration_minutes}m` : "—"}</Td>
                    <Td>{statusLabel(a.source)}</Td>
                    {canManage ? (
                      <Td>
                        <button
                          type="button"
                          className="hos-link-btn"
                          onClick={() => {
                            setCorrectRow(a);
                            setCorrectIn(a.check_in_at.slice(0, 16));
                            setCorrectOut(a.check_out_at ? a.check_out_at.slice(0, 16) : "");
                            setCorrectReason("");
                          }}
                        >
                          Correct
                        </button>
                      </Td>
                    ) : null}
                  </tr>
                ))}
              </Table>
            )}

            {canManage && correctRow && (
              <form onSubmit={onCorrectAttendance} className="hos-att-correct">
                <h3>Correct attendance</h3>
                <p className="hos-muted">
                  Record {correctRow.attendance_date} · {correctRow.id.slice(0, 8)}
                </p>
                <Field label="Check-in" htmlFor="corr-in">
                  {({ describedBy }) => (
                    <Input
                      id="corr-in"
                      type="datetime-local"
                      aria-describedby={describedBy}
                      value={correctIn}
                      onChange={(ev) => setCorrectIn(ev.target.value)}
                    />
                  )}
                </Field>
                <Field label="Check-out" htmlFor="corr-out">
                  {({ describedBy }) => (
                    <Input
                      id="corr-out"
                      type="datetime-local"
                      aria-describedby={describedBy}
                      value={correctOut}
                      onChange={(ev) => setCorrectOut(ev.target.value)}
                    />
                  )}
                </Field>
                <Field label="Reason" htmlFor="corr-reason" required>
                  {({ describedBy }) => (
                    <Input
                      id="corr-reason"
                      aria-describedby={describedBy}
                      value={correctReason}
                      onChange={(ev) => setCorrectReason(ev.target.value)}
                      required
                    />
                  )}
                </Field>
                <div className="hos-inline-actions">
                  <Button type="submit" loading={busy}>
                    Save correction
                  </Button>
                  <Button type="button" variant="secondary" onClick={() => setCorrectRow(null)}>
                    Cancel
                  </Button>
                </div>
              </form>
            )}
          </Card>
        </TabsContent>

        <TabsContent value="leave">
          <p className="hos-caption">
            Leave cancel is not exposed over HTTP. Leave balances are not tracked in this UI.
          </p>
          <Card title="Request leave">
            <form onSubmit={onCreateLeave}>
              <Field label="Type" htmlFor="lv-type">
                {({ describedBy }) => (
                  <Select
                    id="lv-type"
                    aria-describedby={describedBy}
                    value={leaveTypeId}
                    onChange={(ev) => setLeaveTypeId(ev.target.value)}
                    options={leaveTypes.map((t) => ({ value: t.id, label: t.name }))}
                  />
                )}
              </Field>
              <Field label="Start" htmlFor="lv-start" required>
                {({ describedBy }) => (
                  <Input
                    id="lv-start"
                    type="date"
                    aria-describedby={describedBy}
                    value={leaveStart}
                    onChange={(ev) => setLeaveStart(ev.target.value)}
                    required
                  />
                )}
              </Field>
              <Field label="End" htmlFor="lv-end" required>
                {({ describedBy }) => (
                  <Input
                    id="lv-end"
                    type="date"
                    aria-describedby={describedBy}
                    value={leaveEnd}
                    onChange={(ev) => setLeaveEnd(ev.target.value)}
                    required
                  />
                )}
              </Field>
              <Field label="Reason" htmlFor="lv-reason">
                {({ describedBy }) => (
                  <Input
                    id="lv-reason"
                    aria-describedby={describedBy}
                    value={leaveReason}
                    onChange={(ev) => setLeaveReason(ev.target.value)}
                  />
                )}
              </Field>
              <Button type="submit" loading={busy} disabled={busy}>
                Submit request
              </Button>
            </form>
          </Card>

          <Card title="Leave requests">
            <div className="hos-toolbar-row">
              <Field label="Status" htmlFor="lv-filter">
                {({ describedBy }) => (
                  <Select
                    id="lv-filter"
                    aria-describedby={describedBy}
                    value={leaveStatusFilter}
                    onChange={(ev) => setLeaveStatusFilter(ev.target.value)}
                    options={LEAVE_STATUS_FILTERS}
                  />
                )}
              </Field>
              <Button type="button" onClick={() => void reloadLeave()}>
                Refresh
              </Button>
            </div>
            {leaveLoading && leaveRows.length === 0 ? (
              <LoadingState label="Loading leave" />
            ) : leaveRows.length === 0 ? (
              <EmptyState title="No leave requests" />
            ) : (
              <Table
                columns={
                  <>
                    <Th>Type</Th>
                    <Th>Dates</Th>
                    <Th>Status</Th>
                    {canManage ? <Th>Decide</Th> : null}
                  </>
                }
              >
                {leaveRows.map((l) => (
                  <tr key={l.id}>
                    <Td>{l.leave_type_name}</Td>
                    <Td>
                      {l.start_date} → {l.end_date}
                    </Td>
                    <Td>
                      <Status value={l.status} />
                    </Td>
                    {canManage ? (
                      <Td>
                        {l.status === "pending" ? (
                          <div className="hos-inline-actions">
                            <Button
                              type="button"
                              onClick={() => {
                                setLeaveDecideTarget({ row: l, decision: "approved" });
                                setLeaveDecideOpen(true);
                              }}
                            >
                              Approve
                            </Button>
                            <Button
                              type="button"
                              variant="danger"
                              onClick={() => {
                                setLeaveDecideTarget({ row: l, decision: "rejected" });
                                setLeaveDecideOpen(true);
                              }}
                            >
                              Reject
                            </Button>
                          </div>
                        ) : (
                          "—"
                        )}
                      </Td>
                    ) : null}
                  </tr>
                ))}
              </Table>
            )}
          </Card>
        </TabsContent>
      </Tabs>

      <ConfirmDialog
        open={roleConfirmOpen}
        onOpenChange={setRoleConfirmOpen}
        title="Change role"
        confirmLabel="Change role"
        pending={busy}
        onConfirm={() => void confirmRoleChange()}
      >
        Assign role <strong>{pendingRole}</strong> to {profile?.display_name}? Last-admin guard
        may reject this change.
      </ConfirmDialog>

      <ConfirmDialog
        open={revokeOpen}
        onOpenChange={setRevokeOpen}
        title="Revoke invitation"
        confirmLabel="Revoke"
        pending={busy}
        onConfirm={() => void confirmRevokeInvite()}
      >
        Revoke pending invitation for {revokeTarget?.email}?
      </ConfirmDialog>

      <ConfirmDialog
        open={deactSchedOpen}
        onOpenChange={setDeactSchedOpen}
        title="Deactivate schedule"
        confirmLabel="Deactivate"
        pending={busy}
        onConfirm={() => void confirmDeactivateSchedule()}
      >
        Deactivate this staff schedule? This cannot be edited — create a new schedule if hours
        change.
      </ConfirmDialog>

      <ConfirmDialog
        open={rejectOpen}
        onOpenChange={setRejectOpen}
        title="Reject verification"
        confirmLabel="Reject"
        pending={busy}
        onConfirm={() => void confirmRejectVerification()}
      >
        <p>Reject verification for {rejectTarget?.display_name}?</p>
        <Field label="Reason (optional)" htmlFor="rej-reason">
          {({ describedBy }) => (
            <Input
              id="rej-reason"
              aria-describedby={describedBy}
              value={rejectReason}
              onChange={(ev) => setRejectReason(ev.target.value)}
            />
          )}
        </Field>
      </ConfirmDialog>

      <ConfirmDialog
        open={leaveDecideOpen}
        onOpenChange={setLeaveDecideOpen}
        title={
          leaveDecideTarget?.decision === "approved" ? "Approve leave" : "Reject leave"
        }
        confirmLabel={leaveDecideTarget?.decision === "approved" ? "Approve" : "Reject"}
        pending={busy}
        onConfirm={() => void confirmLeaveDecision()}
      >
        <p>
          {leaveDecideTarget?.decision === "approved" ? "Approve" : "Reject"} leave for{" "}
          {leaveDecideTarget?.row.leave_type_name} ({leaveDecideTarget?.row.start_date} –{" "}
          {leaveDecideTarget?.row.end_date})?
        </p>
        <Field label="Note (optional)" htmlFor="lv-note">
          {({ describedBy }) => (
            <Input
              id="lv-note"
              aria-describedby={describedBy}
              value={leaveDecideNote}
              onChange={(ev) => setLeaveDecideNote(ev.target.value)}
            />
          )}
        </Field>
      </ConfirmDialog>
    </div>
  );
}