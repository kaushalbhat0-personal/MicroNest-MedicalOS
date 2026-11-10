"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Field, Input, SkipLink } from "@healthcare-os/ui";
import { api } from "@/lib/api";

type VerifyState = "idle" | "pending" | "ok" | "failed";

export default function VerifyPage() {
  const [token, setToken] = useState("");
  const [status, setStatus] = useState<VerifyState>("idle");
  const [resendEmail, setResendEmail] = useState("");
  const [resent, setResent] = useState(false);
  const [pending, setPending] = useState(false);
  const errorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get("token");
    if (t) setToken(t);
  }, []);

  useEffect(() => {
    if (status === "failed") {
      const el = errorRef.current?.querySelector("[tabindex]");
      (el as HTMLElement | null)?.focus?.();
    }
  }, [status]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setPending(true);
    try {
      await api.post("/api/v1/auth/verify", { token });
      setStatus("ok");
    } catch {
      // Invalid, expired, reused, or superseded links share one message.
      setStatus("failed");
    } finally {
      setPending(false);
    }
  }

  async function resend(e: React.FormEvent) {
    e.preventDefault();
    await api.post("/api/v1/auth/verify/resend", { email: resendEmail });
    // Always 202: identical copy for known and unknown addresses.
    setResent(true);
  }

  if (status === "ok") {
    return (
      <main id="main-content" className="hos-app-main" tabIndex={-1}>
        <SkipLink />
        <Card title="Email verified" headingLevel={1}>
          <p className="hos-helper">Your email is verified. You can now sign in.</p>
          <p>
            <Link href="/login">Sign in</Link>
          </p>
        </Card>
      </main>
    );
  }

  return (
    <main id="main-content" className="hos-app-main" tabIndex={-1}>
      <SkipLink />
      <Card title="Verify email" headingLevel={1}>
        <p className="hos-helper">
          Email verification is optional. Your account works without it; verifying
          adds extra security and can be done at any time.
        </p>
        <form onSubmit={submit} noValidate={false}>
          <Field
            label="Verification code"
            htmlFor="token"
            required
            description="Paste the code from your verification link."
          >
            {({ describedBy }) => (
              <Input
                id="token"
                type="text"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                required
                aria-invalid={status === "failed" ? true : undefined}
                aria-describedby={describedBy}
                autoComplete="one-time-code"
              />
            )}
          </Field>
          {status === "failed" ? (
            <div ref={errorRef}>
              <Alert tone="danger" title="Verification failed">
                <span tabIndex={-1}>
                  This link is invalid or has expired. Request a new one below.
                </span>
              </Alert>
            </div>
          ) : null}
          <p>
            <Button type="submit" loading={pending}>
              Verify email
            </Button>
          </p>
        </form>
      </Card>
      <Card title="Need a new link?">
        {resent ? (
          <p className="hos-helper">
            If an account exists for that email, a new link is on its way.
          </p>
        ) : (
          <form onSubmit={resend} noValidate={false}>
            <Field label="Email" htmlFor="resend-email" required>
              {({ describedBy }) => (
                <Input
                  id="resend-email"
                  type="email"
                  value={resendEmail}
                  onChange={(e) => setResendEmail(e.target.value)}
                  required
                  aria-describedby={describedBy}
                  autoComplete="email"
                />
              )}
            </Field>
            <p>
              <Button type="submit" variant="secondary">
                Resend link
              </Button>
            </p>
          </form>
        )}
      </Card>
    </main>
  );
}
