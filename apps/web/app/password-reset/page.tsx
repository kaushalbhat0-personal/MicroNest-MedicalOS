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
import { api } from "@/lib/api";

function PasswordResetForm() {
  const router = useRouter();
  const params = useSearchParams();
  const tokenFromQuery = params.get("token") ?? "";
  const [email, setEmail] = useState("");
  const [token, setToken] = useState(tokenFromQuery);
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"request" | "confirm">(tokenFromQuery ? "confirm" : "request");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    if (tokenFromQuery) {
      setToken(tokenFromQuery);
      setMode("confirm");
    }
  }, [tokenFromQuery]);

  async function requestReset(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setMessage("");
    setPending(true);
    try {
      await api.post("/api/v1/auth/password-reset/request", { email });
      // Always show the same message (no email oracle).
      setMessage(
        "If an account exists for that email, a reset link was sent. In local development, check the API notification console for the token.",
      );
      setMode("confirm");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setPending(false);
    }
  }

  async function confirmReset(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setMessage("");
    setPending(true);
    try {
      await api.post("/api/v1/auth/password-reset/confirm", {
        token,
        new_password: password,
      });
      setMessage("Password updated. You can sign in now.");
      setTimeout(() => router.push("/login"), 800);
    } catch (err) {
      setError(
        (err as Error).message ||
          "This reset link is invalid or expired. Request a new one.",
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <>
      <PageHeader
        title="Reset password"
        description="Activate a new portal account or recover access. Tokens are verified on the server."
      />
      {error ? (
        <Alert tone="danger" title="Could not reset password">
          {error}
        </Alert>
      ) : null}
      {message ? (
        <Alert tone="success" title="Next step">
          {message}
        </Alert>
      ) : null}

      {mode === "request" ? (
        <Card title="Request a reset link">
          <form onSubmit={requestReset}>
            <Field label="Email" htmlFor="email" required>
              {() => (
                <Input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  autoComplete="email"
                />
              )}
            </Field>
            <p>
              <Button type="submit" loading={pending}>
                Send reset link
              </Button>
            </p>
          </form>
          <p className="hos-helper">
            Portal patients enrolled by the clinic use this flow to set their first password.
          </p>
        </Card>
      ) : (
        <Card title="Choose a new password">
          <form onSubmit={confirmReset}>
            <Field label="Reset token" htmlFor="token" required>
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
            <Field label="New password" htmlFor="password" required>
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
                Update password
              </Button>{" "}
              <Button type="button" variant="secondary" onClick={() => setMode("request")}>
                Request again
              </Button>
            </p>
          </form>
        </Card>
      )}
      <p className="hos-helper">
        <Link href="/login">Back to sign in</Link>
      </p>
    </>
  );
}

export default function PasswordResetPage() {
  return (
    <main id="main-content" className="hos-app-main" tabIndex={-1}>
      <SkipLink />
      <Suspense fallback={<LoadingState label="Loading" />}>
        <PasswordResetForm />
      </Suspense>
    </main>
  );
}
