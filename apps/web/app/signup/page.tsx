"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Alert, Button, Card, Field, Input, SkipLink } from "@healthcare-os/ui";
import { api } from "@/lib/api";

export default function SignupPage() {
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);
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
      await api.post("/api/v1/auth/signup", {
        email,
        display_name: displayName,
        password,
      });
      // 202 for new and existing addresses alike: no account signal here.
      setDone(true);
    } catch (err) {
      // Only shape errors (422) reach this branch; 202 never throws.
      setError(
        err instanceof Error && "status" in err && (err as { status: number }).status === 422
          ? "Check the highlighted fields and try again."
          : "Could not create the account. Try again.",
      );
    } finally {
      setPending(false);
    }
  }

  if (done) {
    return (
      <main id="main-content" className="hos-app-main" tabIndex={-1}>
        <SkipLink />
        <Card title="Account created" headingLevel={1}>
          <p className="hos-helper">
            Your account has been created. Sign in to set up your clinic. Email
            verification is optional and can be completed later.
          </p>
          <p>
            <Link href="/login">Sign in to set up your clinic</Link>
          </p>
          <p className="hos-helper">
            Optional: <Link href="/verify">verify your email later</Link>
          </p>
        </Card>
      </main>
    );
  }

  return (
    <main id="main-content" className="hos-app-main" tabIndex={-1}>
      <SkipLink />
      <Card title="Create account" headingLevel={1}>
        <form onSubmit={submit} noValidate={false}>
          <Field label="Full name" htmlFor="display-name" required>
            {({ describedBy }) => (
              <Input
                id="display-name"
                type="text"
                value={displayName}
                onChange={(e) => setDisplayName(e.target.value)}
                required
                maxLength={200}
                aria-invalid={error ? true : undefined}
                aria-describedby={describedBy}
                autoComplete="name"
              />
            )}
          </Field>
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
          <Field
            label="Password"
            htmlFor="password"
            required
            description="At least 12 characters."
          >
            {({ describedBy }) => (
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={12}
                aria-invalid={error ? true : undefined}
                aria-describedby={describedBy}
                autoComplete="new-password"
              />
            )}
          </Field>
          {error ? (
            <div ref={errorRef}>
              <Alert tone="danger" title="Sign up failed">
                <span tabIndex={-1}>{error}</span>
              </Alert>
            </div>
          ) : null}
          <p>
            <Button type="submit" loading={pending}>
              Create account
            </Button>
          </p>
        </form>
        <p className="hos-helper">
          Already have an account? <Link href="/login">Sign in</Link>
        </p>
      </Card>
    </main>
  );
}
