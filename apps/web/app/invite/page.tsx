"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import {
  Alert,
  Button,
  Card,
  Field,
  Input,
  LoadingState,
  PageHeader,
  SkipLink,
} from "@healthcare-os/ui";
import { api, type Me } from "@/lib/api";
import { setSelectedTenant } from "@/lib/tenant";

function InviteAcceptForm() {
  const router = useRouter();
  const params = useSearchParams();
  const tokenFromQuery = params.get("token") ?? "";
  const [token, setToken] = useState(tokenFromQuery);
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [me, setMe] = useState<Me | null>(null);

  useEffect(() => {
    setToken(tokenFromQuery);
  }, [tokenFromQuery]);

  useEffect(() => {
    let cancelled = false;
    // Non-blocking: show accept form immediately; upgrade to authenticated
    // accept if a session is already present.
    api
      .get<Me>("/api/v1/auth/me")
      .then((m) => {
        if (!cancelled) setMe(m);
      })
      .catch(() => {
        if (!cancelled) setMe(null);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function acceptNew(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setPending(true);
    try {
      const res = await api.post<Me>("/api/v1/invites/accept", {
        token,
        display_name: displayName,
        password,
      });
      if (res.tenants.length === 1) setSelectedTenant(res.tenants[0].id);
      else setSelectedTenant(null);
      router.push("/");
    } catch (err) {
      // API intentionally returns opaque GoneError for bad/expired tokens.
      setError(
        (err as Error).message ||
          "This invitation is invalid or expired. Ask your clinic administrator for a new invite.",
      );
    } finally {
      setPending(false);
    }
  }

  async function acceptAuthenticated(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setPending(true);
    try {
      const res = await api.post<Me>("/api/v1/invites/accept-authenticated", { token });
      if (res.tenants.length === 1) setSelectedTenant(res.tenants[0].id);
      router.push("/");
    } catch (err) {
      setError(
        (err as Error).message ||
          "This invitation is invalid, expired, or does not match your signed-in email.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Accept clinic invitation"
        description="Join your clinic workspace. Invitation details are verified on the server."
      />
      {error ? (
        <Alert tone="danger" title="Invitation could not be accepted">
          {error}
        </Alert>
      ) : null}

      {me ? (
        <Card title="You’re signed in">
          <p className="hos-helper">
            Signed in as {me.display_name} ({me.email}). Your email must match the invitation.
          </p>
          <form onSubmit={acceptAuthenticated}>
            <Field label="Invitation token" htmlFor="token-auth" required>
              {() => (
                <Input
                  id="token-auth"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  required
                  autoComplete="off"
                />
              )}
            </Field>
            <p>
              <Button type="submit" loading={pending}>
                Join workspace
              </Button>
            </p>
          </form>
        </Card>
      ) : (
        <Card title="Create your account">
          <form onSubmit={acceptNew}>
            <Field label="Invitation token" htmlFor="token" required>
              {() => (
                <Input
                  id="token"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                  required
                  autoComplete="off"
                />
              )}
            </Field>
            <Field label="Display name" htmlFor="name" required>
              {() => (
                <Input
                  id="name"
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  required
                  minLength={1}
                  autoComplete="name"
                />
              )}
            </Field>
            <Field label="Password" htmlFor="password" required>
              {() => (
                <Input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  minLength={8}
                  autoComplete="new-password"
                />
              )}
            </Field>
            <p>
              <Button type="submit" loading={pending}>
                Accept invitation
              </Button>
            </p>
          </form>
          <p className="hos-helper">
            Already have an account? <Link href="/login">Sign in</Link>, then return here.
          </p>
        </Card>
      )}
    </>
  );
}

export default function InvitePage() {
  return (
    <main id="main-content" className="hos-app-main" tabIndex={-1}>
      <SkipLink />
      <Suspense fallback={<LoadingState label="Loading invitation" />}>
        <InviteAcceptForm />
      </Suspense>
    </main>
  );
}
