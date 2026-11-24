"use client";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import {
  Alert,
  Badge,
  Button,
  Card,
  EmptyState,
  Field,
  Input,
  LoadingState,
  Select,
  Table,
  Td,
  Th,
  WhatsAppShareAction,
} from "@healthcare-os/ui";
import { api, type Me } from "@/lib/api";
import { staffInviteMessage, staffInviteShareUrl } from "@/lib/shareLinks";
import { getSelectedTenant } from "@/lib/tenant";
import { Shell } from "../shell";

type Member = {
  id: string;
  user_id: string;
  role: string;
  is_active: boolean;
  location_ids?: string[];
};

const ROLES = ["tenant_admin", "doctor", "receptionist", "nurse", "accountant", "staff"];

export default function TeamPage() {
  const router = useRouter();
  const [tenant, setTenant] = useState<string | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("receptionist");
  const [invitePhone, setInvitePhone] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [clinicName, setClinicName] = useState("your clinic");
  const [inviteShare, setInviteShare] = useState<{
    email: string;
    link: string;
    message: string;
    phone: string;
  } | null>(null);

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
    api
      .get<Member[]>(`/api/v1/tenants/${t}/memberships`, t)
      .then((m) => {
        setMembers(m);
        setLoading(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setLoading(false);
      });
  }, [router]);

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    if (!tenant) return;
    setError("");
    setMessage("");
    setInviteShare(null);
    try {
      const res = await api.post<{ token: string; email: string; expires_at?: string }>(
        `/api/v1/tenants/${tenant}/invites`,
        { email, role },
        tenant,
      );
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
        `Invitation created for ${res.email}. Share once via WhatsApp or Copy link.${
          res.expires_at ? ` Expires ${new Date(res.expires_at).toLocaleString()}.` : ""
        }`,
      );
      setEmail("");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function updateMember(id: string, body: { role?: string; is_active?: boolean }) {
    const t = getSelectedTenant();
    if (!t) return;
    setError("");
    try {
      await api.patch(`/api/v1/tenants/${t}/memberships/${id}`, body, t);
      const m = await api.get<Member[]>(`/api/v1/tenants/${t}/memberships`, t);
      setMembers(m);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <Shell>
      <Card title="Team">
        {loading ? (
          <LoadingState label="Loading team" />
        ) : error && members.length === 0 ? (
          <Alert tone="danger" title="Could not load team">
            {error}
          </Alert>
        ) : members.length === 0 ? (
          <EmptyState title="No team members yet">
            Invite the first member below.
          </EmptyState>
        ) : (
          <>
            {error ? (
              <Alert tone="danger" title="Something went wrong">
                {error}
              </Alert>
            ) : null}
            <Table
              caption="Team members"
              columns={
                <>
                  <Th>User</Th>
                  <Th>Role</Th>
                  <Th>Active</Th>
                  <Th>Actions</Th>
                </>
              }
            >
              {members.map((m) => (
                <tr key={m.id}>
                  <Td>{m.user_id.slice(0, 8)}...</Td>
                  <Td>
                    <select
                      className="hos-input"
                      aria-label={`Role for member ${m.user_id.slice(0, 8)}`}
                      value={m.role}
                      onChange={(e) => void updateMember(m.id, { role: e.target.value })}
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {r}
                        </option>
                      ))}
                      {!ROLES.includes(m.role) ? <option value={m.role}>{m.role}</option> : null}
                    </select>
                  </Td>
                  <Td>
                    {m.is_active ? (
                      <Badge tone="success">yes</Badge>
                    ) : (
                      <Badge tone="neutral">no</Badge>
                    )}
                  </Td>
                  <Td>
                    <Button
                      size="sm"
                      variant="secondary"
                      onClick={() => void updateMember(m.id, { is_active: !m.is_active })}
                    >
                      {m.is_active ? "Deactivate" : "Activate"}
                    </Button>
                  </Td>
                </tr>
              ))}
            </Table>
          </>
        )}
      </Card>
      <Card title="Invite member">
        <form onSubmit={invite}>
          <Field label="Email" htmlFor="email" required error={undefined}>
            {({ describedBy }) => (
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                aria-describedby={describedBy}
              />
            )}
          </Field>
          <Field label="Role" htmlFor="role">
            {() => (
              <Select
                id="role"
                value={role}
                onChange={(e) => setRole(e.target.value)}
                options={[
                  { value: "receptionist", label: "receptionist" },
                  { value: "doctor", label: "doctor" },
                  { value: "nurse", label: "nurse" },
                  { value: "accountant", label: "accountant" },
                  { value: "staff", label: "staff" },
                ]}
              />
            )}
          </Field>
          <Field label="WhatsApp phone (optional)" htmlFor="inv-phone">
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
          <p>
            <Button type="submit">Create invitation</Button>
          </p>
        </form>
        {message ? <Alert tone="success">{message}</Alert> : null}
        {inviteShare ? (
          <WhatsAppShareAction
            title="Share invitation"
            contextLabel={`Invitation for ${inviteShare.email}. Single-use; do not forward broadly.`}
            initialPhone={inviteShare.phone}
            initialMessage={inviteShare.message}
            linkToCopy={inviteShare.link}
          />
        ) : null}
      </Card>
    </Shell>
  );
}
