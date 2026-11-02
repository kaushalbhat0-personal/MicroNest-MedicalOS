"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, type Me } from "@/lib/api";
import { setSelectedTenant } from "@/lib/tenant";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const me = await api.post<Me>("/api/v1/auth/login", { email, password });
      // Default to the single tenant; multi-membership users pick on home.
      setSelectedTenant(me.tenants.length === 1 ? me.tenants[0].id : null);
      router.push("/");
    } catch {
      setError("Invalid email or password.");
    }
  }

  return (
    <div className="card">
      <h1>Sign in</h1>
      <form onSubmit={submit}>
        <label htmlFor="email">Email</label>
        <input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        <label htmlFor="password">Password</label>
        <input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
        <p>
          <button type="submit">Sign in</button>
        </p>
        {error && <p className="error">{error}</p>}
      </form>
    </div>
  );
}
