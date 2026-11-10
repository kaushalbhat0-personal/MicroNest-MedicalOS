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
} from "@healthcare-os/ui";
import { api } from "@/lib/api";
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
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const t = getSelectedTenant();
    if (!t) {
      router.push("/");
      return;
    }
    setTenant(t);
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
    try {
      const res = await api.post<{ token: string; email: string }>(
        `/api/v1/tenants/${tenant}/invites`,
        { email, role },
        tenant,
      );
      setMessage(`Invitation created for ${res.email}. Share this once: ${res.token}`);
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
          <p>
            <Button type="submit">Create invitation</Button>
          </p>
        </form>
        {message ? <Alert tone="success">{message}</Alert> : null}
      </Card>
    </Shell>
  );
}
