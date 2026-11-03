"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, type Me } from "@/lib/api";
import { setSelectedTenant } from "@/lib/tenant";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const errorRef = useRef<HTMLParagraphElement>(null);

  // P4.8 a11y: move focus to the error so screen-reader users are told
  // what happened without hunting for the message.
  useEffect(() => {
    if (error) errorRef.current?.focus();
  }, [error ]);

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
        <input
          id="email"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "login-error" : undefined}
        />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? "login-error" : undefined}
        />
        <p>
          <button type="submit">Sign in</button>
        </p>
        {error && (
          <p
            id="login-error"
            ref={errorRef}
            tabIndex={-1}
            role="alert"
            className="error"
          >
            {error}
          </p>
        )}
      </form>
    </div>
  );
}
