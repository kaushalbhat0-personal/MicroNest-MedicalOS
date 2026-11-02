"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

type SessionInfo = { id: string; created_at: string; ip: string | null; current: boolean };

export default function SessionsPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionInfo[]>([]);
  const [error, setError] = useState("");

  function load() {
    api
      .get<SessionInfo[]>("/api/v1/auth/sessions")
      .then(setSessions)
      .catch(() => router.push("/login"));
  }

  useEffect(load, [router]);

  async function revoke(id: string) {
    try {
      await api.del(`/api/v1/auth/sessions/${id}`);
      load();
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
      </nav>
      <div className="card">
        <h1>Sessions</h1>
        {error && <p className="error">{error}</p>}
        <table>
          <thead>
            <tr>
              <th>Started</th>
              <th>IP</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id}>
                <td>
                  {new Date(s.created_at).toLocaleString()}
                  {s.current ? " (this device)" : ""}
                </td>
                <td>{s.ip ?? "—"}</td>
                <td>{!s.current && <button onClick={() => void revoke(s.id)}>Revoke</button>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
