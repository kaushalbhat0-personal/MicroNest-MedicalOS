"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  LoadingState,
  PageHeader,
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
import { staffInviteMessage, staffInviteShareUrl } from "@/lib/shareLinks";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../shell";

type InviteShare = {
  email: string;
  link: string;
  message: string;
  phone: string;
};

type Location = { id: string; name: string };
type Staff = {
  membership_id: string;
  user_id: string;
  email: string;
  display_name: string;
  role: string;
  permissions: string[];
  is_active: boolean;
  location_ids: string[];
  designation: string | null;
  phone: string | null;
  employment_status: string;
  joined_at: string | null;
};
type Invitation = {
  id: string;
  email: string;
  role: string;
  status: string;
  expires_at: string;
};
type Schedule = {
  id: string;
  membership_id: string;
  location_id: string;
  weekday: number;
  start_time: string;
  end_time: string;
  break_minutes: number;
};
type Attendance = {
  id: string;
  membership_id: string;
  location_id: string;
  attendance_date: string;
  check_in_at: string;
  check_out_at: string | null;
  source: string;
  duration_minutes: number | null;
};
type LeaveType = { id: string; name: string };
type Leave = {
  id: string;
  membership_id: string;
  leave_type_name: string;
  start_date: string;
  end_date: string;
  status: string;
  reason: string | null;
};

const ROLES = ["tenant_admin", "doctor", "receptionist", "nurse", "accountant", "staff"];
const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export default function StaffPage() {
  const router = useRouter();
  const [tenant, setTenant] = useState<string | null>(null);
  const [locations, setLocations] = useState<Location[]>([]);
  const [locationId, setLocationId] = useState("");
  const [staff, setStaff] = useState<Staff[]>([]);
  const [invites, setInvites] = useState<Invitation[]>([]);
  const [schedules, setSchedules] = useState<Schedule[]>([]);
  const [attendance, setAttendance] = useState<Attendance[]>([]);
  const [leaveTypes, setLeaveTypes] = useState<LeaveType[]>([]);
  const [leaves, setLeaves] = useState<Leave[]>([]);
  const [selected, setSelected] = useState<Staff | null>(null);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState("receptionist");
  const [invitePhone, setInvitePhone] = useState("");
  const [inviteShare, setInviteShare] = useState<InviteShare | null>(null);
  const [clinicName, setClinicName] = useState("your clinic");
  const [designation, setDesignation] = useState("");
  const [phone, setPhone] = useState("");
  const [schedMember, setSchedMember] = useState("");
  const [schedWeekday, setSchedWeekday] = useState("0");
  const [schedStart, setSchedStart] = useState("09:00");
  const [schedEnd, setSchedEnd] = useState("17:00");
  const [leaveTypeId, setLeaveTypeId] = useState("");
  const [leaveStart, setLeaveStart] = useState("");
  const [leaveEnd, setLeaveEnd] = useState("");
  const [leaveReason, setLeaveReason] = useState("");

  const load = useCallback(async (tid: string) => {
    setError("");
    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    if (locationId) qs.set("location_id", locationId);
    const [locs, members, inv, sched, att, ltypes, leaveRows] = await Promise.all([
      api.get<Location[]>(`/api/v1/tenants/${tid}/locations`, tid),
      api.get<Staff[]>(`/api/v1/tenants/${tid}/staff?${qs}`, tid),
      api.get<Invitation[]>(`/api/v1/tenants/${tid}/invitations`, tid).catch(() => []),
      api.get<Schedule[]>(`/api/v1/tenants/${tid}/staff-schedules`, tid).catch(() => []),
      api.get<Attendance[]>(`/api/v1/tenants/${tid}/attendance`, tid).catch(() => []),
      api.get<LeaveType[]>(`/api/v1/tenants/${tid}/leave-types`, tid).catch(() => []),
      api.get<Leave[]>(`/api/v1/tenants/${tid}/leave-requests`, tid).catch(() => []),
    ]);
    setLocations(locs);
    setStaff(members);
    setInvites(inv);
    setSchedules(sched);
    setAttendance(att);
    setLeaveTypes(ltypes);
    setLeaves(leaveRows);
    if (!leaveTypeId && ltypes[0]) setLeaveTypeId(ltypes[0].id);
    if (!schedMember && members[0]) setSchedMember(members[0].membership_id);
    setLoading(false);
  }, [locationId, leaveTypeId, q, schedMember]);

  useEffect(() => {
    const t = getSelectedTenant();
    if (!t) {
      router.push("/");
      return;
    }
    setTenant(t);
    api
      .get<Me>("/api/v1/auth/me")
      .then((me) => {
        const match = me.tenants.find((x) => x.id === t);
        if (match?.name) setClinicName(match.name);
      })
      .catch(() => undefined);
    load(t).catch((e: Error) => {
      setError(e.message);
      setLoading(false);
    });
  }, [router, load]);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    if (!tenant) return;
    setError("");
    setMessage("");
    setInviteShare(null);
    try {
      const body: { email: string; role: string; location_ids?: string[] } = {
        email: inviteEmail,
        role: inviteRole,
      };
      if (locationId) body.location_ids = [locationId];
      const res = await api.post<{ token: string; email: string; expires_at?: string }>(
        `/api/v1/tenants/${tenant}/invites`,
        body,
        tenant,
      );
      // Token stays in component state for one-time share UI — not written to console.
      const link = staffInviteShareUrl(res.token);
      setInviteShare({
        email: res.email,
        link,
        phone: invitePhone.trim(),
        message: staffInviteMessage({
          clinicName,
          inviteUrl: link,
          expiresAt: res.expires_at,
        }),
      });
      setMessage(
        `Invitation created for ${res.email}. Share it once via WhatsApp or Copy link below.${
          res.expires_at ? ` Expires ${new Date(res.expires_at).toLocaleString()}.` : ""
        }`,
      );
      setInviteEmail("");
      await load(tenant);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function saveProfile(e: React.FormEvent) {
    e.preventDefault();
    if (!tenant || !selected) return;
    setError("");
    try {
      await api.patch(
        `/api/v1/tenants/${tenant}/staff/${selected.membership_id}`,
        { designation, phone },
        tenant,
      );
      setMessage("Profile updated");
      await load(tenant);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function revokeInvite(id: string) {
    if (!tenant) return;
    await api.post(`/api/v1/tenants/${tenant}/invitations/${id}/revoke`, {}, tenant);
    await load(tenant);
  }

  async function addSchedule(e: React.FormEvent) {
    e.preventDefault();
    if (!tenant || !locationId) {
      setError("Select a location for the schedule");
      return;
    }
    try {
      await api.post(
        `/api/v1/tenants/${tenant}/staff-schedules`,
        {
          membership_id: schedMember,
          location_id: locationId,
          weekday: Number(schedWeekday),
          start_time: `${schedStart}:00`,
          end_time: `${schedEnd}:00`,
          break_minutes: 60,
          effective_from: new Date().toISOString().slice(0, 10),
        },
        tenant,
      );
      setMessage("Schedule created");
      await load(tenant);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function checkIn() {
    if (!tenant || !locationId) {
      setError("Select a location to check in");
      return;
    }
    try {
      await api.post(
        `/api/v1/tenants/${tenant}/attendance/check-in`,
        { location_id: locationId },
        tenant,
      );
      setMessage("Checked in");
      await load(tenant);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function checkOut() {
    if (!tenant) return;
    try {
      await api.post(`/api/v1/tenants/${tenant}/attendance/check-out`, {}, tenant);
      setMessage("Checked out");
      await load(tenant);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function requestLeave(e: React.FormEvent) {
    e.preventDefault();
    if (!tenant) return;
    try {
      await api.post(
        `/api/v1/tenants/${tenant}/leave-requests`,
        {
          leave_type_id: leaveTypeId,
          start_date: leaveStart,
          end_date: leaveEnd,
          reason: leaveReason || null,
        },
        tenant,
      );
      setMessage("Leave requested");
      await load(tenant);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function decideLeave(id: string, decision: "approved" | "rejected") {
    if (!tenant) return;
    try {
      await api.post(
        `/api/v1/tenants/${tenant}/leave-requests/${id}/decide`,
        { decision },
        tenant,
      );
      await load(tenant);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Shell>
      <PageHeader title="Staff" description="Directory, roles, attendance and leave" />
      {error ? (
        <Alert tone="danger" title="Error">
          {error}
        </Alert>
      ) : null}
      {message ? (
        <Alert tone="success" title="Done">
          {message}
        </Alert>
      ) : null}
      <Field label="Location" htmlFor="staff-loc">
        {() => (
          <select
            id="staff-loc"
            className="hos-input"
            value={locationId}
            onChange={(e) => setLocationId(e.target.value)}
          >
            <option value="">All locations</option>
            {locations.map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
        )}
      </Field>
      {loading ? (
        <LoadingState label="Loading staff" />
      ) : (
        <Tabs defaultValue="directory">
          <TabsList>
            <TabsTrigger value="directory">Directory</TabsTrigger>
            <TabsTrigger value="profile">Profile</TabsTrigger>
            <TabsTrigger value="roles">Roles</TabsTrigger>
            <TabsTrigger value="invites">Invitations</TabsTrigger>
            <TabsTrigger value="schedules">Schedules</TabsTrigger>
            <TabsTrigger value="attendance">Attendance</TabsTrigger>
            <TabsTrigger value="leave">Leave</TabsTrigger>
          </TabsList>

          <TabsContent value="directory">
            <Card title="Staff directory">
              <Field label="Search" htmlFor="staff-q">
                {() => (
                  <Input id="staff-q" value={q} onChange={(e) => setQ(e.target.value)} />
                )}
              </Field>
              <Button type="button" onClick={() => tenant && load(tenant)}>
                Apply filters
              </Button>
              {staff.length === 0 ? (
                <EmptyState title="No staff found" />
              ) : (
                <Table
                  caption="Staff members"
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
                  {staff.map((s) => (
                    <tr key={s.membership_id}>
                      <Td>
                        <button
                          type="button"
                          className="hos-link"
                          onClick={() => {
                            setSelected(s);
                            setDesignation(s.designation || "");
                            setPhone(s.phone || "");
                          }}
                        >
                          {s.display_name}
                        </button>
                      </Td>
                      <Td>{s.email}</Td>
                      <Td>{s.role}</Td>
                      <Td>{s.designation || "—"}</Td>
                      <Td>
                        <Status value={s.is_active ? s.employment_status : "inactive"} />
                      </Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
          </TabsContent>

          <TabsContent value="profile">
            <Card title="Staff profile">
              {!selected ? (
                <EmptyState title="Select a staff member from Directory" />
              ) : (
                <form onSubmit={saveProfile}>
                  <p>
                    <strong>{selected.display_name}</strong> · {selected.email}
                  </p>
                  <Field label="Designation" htmlFor="desig">
                    {() => (
                      <Input
                        id="desig"
                        value={designation}
                        onChange={(e) => setDesignation(e.target.value)}
                      />
                    )}
                  </Field>
                  <Field label="Phone" htmlFor="phone">
                    {() => (
                      <Input id="phone" value={phone} onChange={(e) => setPhone(e.target.value)} />
                    )}
                  </Field>
                  <p>Joined: {selected.joined_at || "—"}</p>
                  <p>Locations: {selected.location_ids.length || "all"}</p>
                  <Button type="submit">Save profile</Button>
                </form>
              )}
            </Card>
          </TabsContent>

          <TabsContent value="roles">
            <Card title="Roles and effective permissions">
              {!selected ? (
                <EmptyState title="Select a staff member" />
              ) : (
                <>
                  <p>
                    Role: <Badge tone="info">{selected.role}</Badge>
                  </p>
                  <Field label="Change role" htmlFor="role-chg">
                    {() => (
                      <Select
                        id="role-chg"
                        value={selected.role}
                        options={ROLES.map((r) => ({ value: r, label: r }))}
                        onChange={async (e) => {
                          if (!tenant) return;
                          await api.patch(
                            `/api/v1/tenants/${tenant}/staff/${selected.membership_id}`,
                            { role: e.target.value },
                            tenant,
                          );
                          await load(tenant);
                        }}
                      />
                    )}
                  </Field>
                  <ul>
                    {selected.permissions.map((p) => (
                      <li key={p}>{p}</li>
                    ))}
                  </ul>
                </>
              )}
            </Card>
          </TabsContent>

          <TabsContent value="invites">
            <Card title="Invite staff">
              <form onSubmit={invite}>
                <Field label="Email" htmlFor="inv-email" required>
                  {() => (
                    <Input
                      id="inv-email"
                      type="email"
                      value={inviteEmail}
                      onChange={(e) => setInviteEmail(e.target.value)}
                      required
                    />
                  )}
                </Field>
                <Field label="Role" htmlFor="inv-role">
                  {() => (
                    <Select
                      id="inv-role"
                      value={inviteRole}
                      options={ROLES.map((r) => ({ value: r, label: r }))}
                      onChange={(e) => setInviteRole(e.target.value)}
                    />
                  )}
                </Field>
                <Field
                  label="WhatsApp phone (optional)"
                  htmlFor="inv-phone"
                  description="Used only to open WhatsApp after create. Invitation is still email-scoped on the server."
                >
                  {() => (
                    <Input
                      id="inv-phone"
                      type="tel"
                      value={invitePhone}
                      onChange={(e) => setInvitePhone(e.target.value)}
                      placeholder="+91…"
                      autoComplete="tel"
                    />
                  )}
                </Field>
                <Button type="submit">Create invitation</Button>
              </form>
              {inviteShare ? (
                <WhatsAppShareAction
                  title="Share invitation"
                  contextLabel={`Staff invitation for ${inviteShare.email} · role ${inviteRole}. Link is single-use and expires.`}
                  initialPhone={inviteShare.phone}
                  initialMessage={inviteShare.message}
                  linkToCopy={inviteShare.link}
                  confirmLabel="I understand this opens WhatsApp with the invite link. Nothing is sent until I tap send in WhatsApp."
                />
              ) : null}
            </Card>
            <Card title="Pending invitations">
              {invites.filter((i) => i.status === "pending").length === 0 ? (
                <EmptyState title="No pending invitations" />
              ) : (
                <Table
                  caption="Invitations"
                  columns={
                    <>
                      <Th>Email</Th>
                      <Th>Role</Th>
                      <Th>Expires</Th>
                      <Th>Actions</Th>
                    </>
                  }
                >
                  {invites
                    .filter((i) => i.status === "pending")
                    .map((i) => (
                      <tr key={i.id}>
                        <Td>{i.email}</Td>
                        <Td>{i.role}</Td>
                        <Td>{new Date(i.expires_at).toLocaleString()}</Td>
                        <Td>
                          <Button type="button" onClick={() => revokeInvite(i.id)}>
                            Revoke
                          </Button>
                        </Td>
                      </tr>
                    ))}
                </Table>
              )}
            </Card>
          </TabsContent>

          <TabsContent value="schedules">
            <Card title="Working schedules">
              <p>Staff schedules are separate from clinic hours and practitioner availability.</p>
              <form onSubmit={addSchedule}>
                <Field label="Staff" htmlFor="sch-m">
                  {() => (
                    <Select
                      id="sch-m"
                      value={schedMember}
                      options={staff.map((s) => ({
                        value: s.membership_id,
                        label: s.display_name,
                      }))}
                      onChange={(e) => setSchedMember(e.target.value)}
                    />
                  )}
                </Field>
                <Field label="Weekday" htmlFor="sch-d">
                  {() => (
                    <Select
                      id="sch-d"
                      value={schedWeekday}
                      options={WEEKDAYS.map((d, i) => ({
                        value: String(i),
                        label: d,
                      }))}
                      onChange={(e) => setSchedWeekday(e.target.value)}
                    />
                  )}
                </Field>
                <Field label="Start" htmlFor="sch-s">
                  {() => (
                    <Input
                      id="sch-s"
                      type="time"
                      value={schedStart}
                      onChange={(e) => setSchedStart(e.target.value)}
                    />
                  )}
                </Field>
                <Field label="End" htmlFor="sch-e">
                  {() => (
                    <Input
                      id="sch-e"
                      type="time"
                      value={schedEnd}
                      onChange={(e) => setSchedEnd(e.target.value)}
                    />
                  )}
                </Field>
                <Button type="submit">Add schedule</Button>
              </form>
              {schedules.length === 0 ? (
                <EmptyState title="No schedules" />
              ) : (
                <Table
                  caption="Schedules"
                  columns={
                    <>
                      <Th>Day</Th>
                      <Th>Hours</Th>
                      <Th>Break</Th>
                    </>
                  }
                >
                  {schedules.map((s) => (
                    <tr key={s.id}>
                      <Td>{WEEKDAYS[s.weekday]}</Td>
                      <Td>
                        {s.start_time} – {s.end_time}
                      </Td>
                      <Td>{s.break_minutes}m</Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
          </TabsContent>

          <TabsContent value="attendance">
            <Card title="Attendance">
              <div style={{ display: "flex", gap: "0.5rem" }}>
                <Button type="button" onClick={checkIn}>
                  Check in
                </Button>
                <Button type="button" onClick={checkOut}>
                  Check out
                </Button>
              </div>
              {attendance.length === 0 ? (
                <EmptyState title="No attendance records" />
              ) : (
                <Table
                  caption="Attendance history"
                  columns={
                    <>
                      <Th>Date</Th>
                      <Th>In</Th>
                      <Th>Out</Th>
                      <Th>Duration</Th>
                      <Th>Source</Th>
                    </>
                  }
                >
                  {attendance.map((a) => (
                    <tr key={a.id}>
                      <Td>{a.attendance_date}</Td>
                      <Td>{new Date(a.check_in_at).toLocaleTimeString()}</Td>
                      <Td>
                        {a.check_out_at
                          ? new Date(a.check_out_at).toLocaleTimeString()
                          : "—"}
                      </Td>
                      <Td>{a.duration_minutes ?? "—"}</Td>
                      <Td>{a.source}</Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
          </TabsContent>

          <TabsContent value="leave">
            <Card title="Request leave">
              <form onSubmit={requestLeave}>
                <Field label="Type" htmlFor="lt">
                  {() => (
                    <Select
                      id="lt"
                      value={leaveTypeId}
                      options={leaveTypes.map((t) => ({
                        value: t.id,
                        label: t.name,
                      }))}
                      onChange={(e) => setLeaveTypeId(e.target.value)}
                    />
                  )}
                </Field>
                <Field label="Start" htmlFor="ls">
                  {() => (
                    <Input
                      id="ls"
                      type="date"
                      value={leaveStart}
                      onChange={(e) => setLeaveStart(e.target.value)}
                      required
                    />
                  )}
                </Field>
                <Field label="End" htmlFor="le">
                  {() => (
                    <Input
                      id="le"
                      type="date"
                      value={leaveEnd}
                      onChange={(e) => setLeaveEnd(e.target.value)}
                      required
                    />
                  )}
                </Field>
                <Field label="Reason" htmlFor="lr">
                  {() => (
                    <Input
                      id="lr"
                      value={leaveReason}
                      onChange={(e) => setLeaveReason(e.target.value)}
                    />
                  )}
                </Field>
                <Button type="submit">Submit request</Button>
              </form>
            </Card>
            <Card title="Leave history">
              {leaves.length === 0 ? (
                <EmptyState title="No leave requests" />
              ) : (
                <Table
                  caption="Leave"
                  columns={
                    <>
                      <Th>Type</Th>
                      <Th>Dates</Th>
                      <Th>Status</Th>
                      <Th>Actions</Th>
                    </>
                  }
                >
                  {leaves.map((l) => (
                    <tr key={l.id}>
                      <Td>{l.leave_type_name}</Td>
                      <Td>
                        {l.start_date} → {l.end_date}
                      </Td>
                      <Td>
                        <Status value={l.status} />
                      </Td>
                      <Td>
                        {l.status === "pending" ? (
                          <>
                            <Button type="button" onClick={() => decideLeave(l.id, "approved")}>
                              Approve
                            </Button>{" "}
                            <Button type="button" onClick={() => decideLeave(l.id, "rejected")}>
                              Reject
                            </Button>
                          </>
                        ) : null}
                      </Td>
                    </tr>
                  ))}
                </Table>
              )}
            </Card>
          </TabsContent>
        </Tabs>
      )}
    </Shell>
  );
}
