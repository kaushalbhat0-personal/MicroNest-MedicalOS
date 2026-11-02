"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { getSelectedTenant } from "@/lib/tenant";

type Member = { id: string; user_id: string; role: string; is_active: boolean };

export default function TeamPage() {
  const router = useRouter();
  const [tenant, setTenant] = useState<string | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
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
      .then(setMembers)
      .catch((e: Error) => setError(e.message));
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

  return (
    <>
      <nav>
        <Link href="/">Home</Link>
        <Link href="/team">Team</Link>
        <Link href="/sessions">Sessions</Link>
        <Link href="/schedule">Schedule</Link>
        <Link href="/encounters">Encounters</Link>
      </nav>
      <div className="card">
        <h1>Team</h1>
        {error && <p className="error">{error}</p>}
        <table>
          <thead>
            <tr>
              <th>User</th>
              <th>Role</th>
              <th>Active</th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id}>
                <td>{m.user_id.slice(0, 8)}…</td>
                <td>{m.role}</td>
                <td>{m.is_active ? "yes" : "no"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card">
        <h2>Invite member</h2>
        <form onSubmit={invite}>
          <label htmlFor="email">Email</label>
          <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
          <label htmlFor="role">Role</label>
          <select id="role" value={role} onChange={(e) => setRole(e.target.value)}>
            <option value="receptionist">receptionist</option>
            <option value="doctor">doctor</option>
            <option value="nurse">nurse</option>
            <option value="accountant">accountant</option>
            <option value="staff">staff</option>
          </select>
          <p>
            <button type="submit">Create invitation</button>
          </p>
        </form>
        {message && <p>{message}</p>}
      </div>
    </>
  );
}
