"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type Me } from "@/lib/api";
import { getSelectedTenant, setSelectedTenant } from "@/lib/tenant";

export default function HomePage() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [tenant, setTenant] = useState<string | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .get<Me>("/api/v1/auth/me")
      .then((m) => {
        setMe(m);
        const sel = getSelectedTenant();
        setTenant(sel ?? (m.tenants.length === 1 ? m.tenants[0].id : null));
      })
      .catch(() => router.push("/login"));
  }, [router]);

  if (!me) return <p className="muted">Loading…</p>;

  function pick(id: string) {
    setSelectedTenant(id);
    setTenant(id);
  }

  async function logout() {
    await api.post("/api/v1/auth/logout");
    setSelectedTenant(null);
    router.push("/login");
  }

  return (
    <>
      <nav>
        <Link href="/">Home</Link>
        <Link href="/team">Team</Link>
        <Link href="/sessions">Sessions</Link>
      </nav>
      <div className="card">
        <h1>Welcome, {me.display_name}</h1>
        <p className="muted">{me.email}</p>
        {error && <p className="error">{error}</p>}
        <label htmlFor="tenant">Tenant</label>
        <select
          id="tenant"
          value={tenant ?? ""}
          onChange={(e) => pick(e.target.value)}
        >
          <option value="" disabled>
            Select a tenant
          </option>
          {me.tenants.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name} ({t.slug})
            </option>
          ))}
        </select>
        {!tenant && <p className="muted">Select a tenant to continue.</p>}
        <p>
          <button className="secondary" onClick={() => void logout()}>
            Sign out
          </button>
        </p>
      </div>
      {tenant && (
        <div className="card">
          <h2>Tenant</h2>
          <TenantDetail id={tenant} onError={setError} />
        </div>
      )}
    </>
  );
}

function TenantDetail({ id, onError }: { id: string; onError: (e: string) => void }) {
  const [detail, setDetail] = useState<{ name: string; slug: string; status: string } | null>(null);
  const [locations, setLocations] = useState<{ id: string; name: string }[]>([]);
  useEffect(() => {
    api
      .get<{ name: string; slug: string; status: string }>(`/api/v1/tenants/${id}`, id)
      .then(setDetail)
      .catch((e: Error) => onError(e.message));
    api
      .get<{ id: string; name: string }[]>(`/api/v1/tenants/${id}/locations`, id)
      .then(setLocations)
      .catch(() => {});
  }, [id, onError]);
  if (!detail) return <p className="muted">Loading tenant…</p>;
  return (
    <>
      <p>
        {detail.name} · {detail.slug} · {detail.status}
      </p>
      <h3>Locations</h3>
      <ul>
        {locations.map((l) => (
          <li key={l.id}>{l.name}</li>
        ))}
      </ul>
    </>
  );
}
