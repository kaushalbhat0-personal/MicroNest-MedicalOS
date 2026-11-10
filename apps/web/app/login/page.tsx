"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Field, Input, SkipLink } from "@healthcare-os/ui";
import { api, type Me } from "@/lib/api";
import { type PortalWorkspaces } from "@/lib/portal";
import { setSelectedTenant } from "@/lib/tenant";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error) {
      const el = errorRef.current?.querySelector("[tabindex]");
      (el as HTMLElement | null)?.focus?.();
    }
  }, [error]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setPending(true);
    try {
      const me = await api.post<Me>("/api/v1/auth/login", { email, password });
      // Server-authoritative workspace routing: the portal link set decides.
      const ws = await api
        .get<PortalWorkspaces>("/api/v1/portal/workspaces")
        .catch(() => ({ provider: true, portal: false }));
      if (ws.portal && !ws.provider) {
        // Portal-only identity: resolve the tenant for deep links, then home.
        const full = await api.get<Me>("/api/v1/auth/me").catch(() => me);
        const list = full.tenants.length > 0 ? full.tenants : me.tenants;
        setSelectedTenant(list.length === 1 ? list[0].id : null);
        router.push("/portal");
        return;
      }
      // Default to the single tenant; multi-membership users pick on home.
      setSelectedTenant(me.tenants.length === 1 ? me.tenants[0].id : null);
      router.push("/");
    } catch {
      setError("Invalid email or password.");
    } finally {
      setPending(false);
    }
  }

  return (
    <main id="main-content" className="hos-app-main" tabIndex={-1}>
      <SkipLink />
      <Card title="Sign in" headingLevel={1}>
        <form onSubmit={submit} noValidate={false}>
          <Field label="Email" htmlFor="email" required>
            {({ describedBy }) => (
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                aria-invalid={error ? true : undefined}
                aria-describedby={describedBy}
                autoComplete="email"
              />
            )}
          </Field>
          <Field label="Password" htmlFor="password" required>
            {({ describedBy }) => (
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                aria-invalid={error ? true : undefined}
                aria-describedby={describedBy}
                autoComplete="current-password"
              />
            )}
          </Field>
          {error ? (
            <div ref={errorRef}>
              <Alert tone="danger" title="Sign in failed">
                <span tabIndex={-1}>{error}</span>
              </Alert>
            </div>
          ) : null}
          <p>
            <Button type="submit" loading={pending}>
              Sign in
            </Button>
          </p>
        </form>
        <p className="hos-helper">
          New here? <Link href="/signup">Create an account</Link>
        </p>
      </Card>
    </main>
  );
}
