import { FormEvent, useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import {
  Alert,
  Button,
  Card,
  ErrorState,
  Field,
  Input,
  LoadingState,
} from "@healthcare-os/ui";
import { Dashboard } from "./components/Dashboard";
import { ModulePlaceholder, Shell } from "./components/Shell";
import { PatientsDirectory } from "./components/patients/PatientsDirectory";
import { PatientProfile } from "./components/patients/PatientProfile";
import { BillingHub } from "./components/billing/BillingHub";
import { TreatmentPlansHub } from "./components/dental/TreatmentPlansHub";
import { StaffHub } from "./components/staff/StaffHub";
import { DoctorConsultBoard } from "./components/clinical/DoctorConsultBoard";
import { EncounterWorkspace } from "./components/clinical/EncounterWorkspace";
import { ReceptionQueue } from "./components/reception/ReceptionQueue";
import { ScheduleCalendar } from "./components/schedule/ScheduleCalendar";
import {
  fetchMe,
  getAccessToken,
  nativeLogin,
  nativeLogout,
  nativeRefresh,
  probeHealth,
  tryRestoreSession,
} from "./lib/api";
import { getApiBaseUrl, getChannel } from "./lib/config";
import { SessionProvider, useSession } from "./lib/session";
import { SecureTokenStore } from "./lib/secureStore";

type Phase =
  | "booting"
  | "login"
  | "workspace"
  | "ready"
  | "session_expired"
  | "offline";

function parseRoute(route: string): {
  base: string;
  patientId: string | null;
  encounterId: string | null;
  queryPatient: string | null;
  queryAppointment: string | null;
  queryEstimate: string | null;
  queryInvoice: string | null;
  billingTab: "estimates" | "invoices" | "payments" | "dues" | "refunds" | "credits" | null;
} {
  const [pathPart, query = ""] = route.split("?");
  const params = new URLSearchParams(query);
  const queryPatient = params.get("patient");
  const queryAppointment = params.get("appointment");
  const queryEstimate = params.get("estimate");
  const queryInvoice = params.get("invoice");
  const tabParam = params.get("tab");
  const billingTab =
    tabParam === "estimates" ||
    tabParam === "invoices" ||
    tabParam === "payments" ||
    tabParam === "dues" ||
    tabParam === "refunds" ||
    tabParam === "credits"
      ? tabParam
      : null;
  const patientMatch = pathPart.match(/^\/patients\/([^/?]+)$/);
  if (patientMatch && patientMatch[1] !== "new") {
    return {
      base: "/patients",
      patientId: patientMatch[1],
      encounterId: null,
      queryPatient,
      queryAppointment,
      queryEstimate,
      queryInvoice,
      billingTab,
    };
  }
  const encMatch = pathPart.match(/^\/encounters\/([^/?]+)$/);
  if (encMatch) {
    return {
      base: "/encounters",
      patientId: null,
      encounterId: encMatch[1],
      queryPatient,
      queryAppointment,
      queryEstimate,
      queryInvoice,
      billingTab,
    };
  }
  // Normalize all /billing/* nav to billing hub
  if (pathPart.startsWith("/billing")) {
    return {
      base: "/billing/invoices",
      patientId: null,
      encounterId: null,
      queryPatient,
      queryAppointment,
      queryEstimate,
      queryInvoice,
      billingTab:
        billingTab ??
        (pathPart.includes("estimates")
          ? "estimates"
          : pathPart.includes("payments")
            ? "payments"
            : pathPart.includes("dues")
              ? "dues"
              : "invoices"),
    };
  }
  return {
    base: pathPart || "/",
    patientId: null,
    encounterId: null,
    queryPatient,
    queryAppointment,
    queryEstimate,
    queryInvoice,
    billingTab,
  };
}

function AppInner() {
  const session = useSession();
  const [phase, setPhase] = useState<Phase>("booting");
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [apiBase, setApiBase] = useState("");
  const [channel, setChannel] = useState("development");
  const [route, setRoute] = useState("/");
  const [logoutNote, setLogoutNote] = useState<string | null>(null);
  /** Cleared on workspace switch / logout — never cache across clinics. */
  const [patientViewId, setPatientViewId] = useState<string | null>(null);
  const [encounterViewId, setEncounterViewId] = useState<string | null>(null);

  const parsed = parseRoute(route);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [base, ch] = await Promise.all([getApiBaseUrl(), getChannel()]);
        if (!cancelled) {
          setApiBase(base);
          setChannel(ch);
        }
        const ok = await probeHealth();
        if (!ok) throw new Error("health");

        let auto: { email: string; password: string } | null = null;
        try {
          auto = await invoke("get_m3_autologin");
        } catch {
          auto = null;
        }
        if (auto?.email) {
          await SecureTokenStore.clearSession().catch(() => undefined);
          const body = await nativeLogin(auto.email, auto.password);
          if (cancelled) return;
          session.setProfile(body);
          if (body.tenants[0]) await session.selectTenant(body.tenants[0]);
          const me = await fetchMe(body.tenants[0]?.id);
          const beforeRefresh = await invoke<{ exists: boolean }>(
            "evidence_refresh_file_state",
          );
          const rotated = await nativeRefresh();
          const afterRefresh = await invoke<{
            exists: boolean;
            looks_like_json_envelope?: boolean;
            contains_dot_token_shape?: boolean;
          }>("evidence_refresh_file_state");
          const me2 = await fetchMe(body.tenants[0]?.id);
          await nativeLogout();
          const afterLogout = await invoke<{ exists: boolean }>(
            "evidence_refresh_file_state",
          );
          const evidence = {
            phase: "M3",
            channel: ch,
            api_base: base,
            login: true,
            workspace_selected: Boolean(body.tenants[0]),
            me_email_matches: me.email === body.email,
            refresh_file_after_login: beforeRefresh,
            refresh_rotated: Boolean(rotated.session_id),
            refresh_file_after_rotate: afterRefresh,
            me_after_refresh: me2.email === body.email,
            logout_cleared_dpapi: afterLogout.exists === false,
            access_in_memory_after_logout: getAccessToken() === null,
            tokens_in_evidence: false,
          };
          await invoke<string>("write_runtime_evidence", {
            json: JSON.stringify(evidence, null, 2),
          });
          const again = await nativeLogin(auto.email, auto.password);
          if (cancelled) return;
          session.setProfile(again);
          if (again.tenants[0]) await session.selectTenant(again.tenants[0]);
          setPhase("ready");
          return;
        }

        const restored = await tryRestoreSession();
        if (cancelled) return;
        if (restored) {
          session.setProfile(restored);
          if (restored.tenants.length === 1) {
            await session.selectTenant(restored.tenants[0]);
            setPhase("ready");
          } else if (restored.tenants.length > 1) {
            setPhase("workspace");
          } else {
            setPhase("ready");
          }
        } else {
          setPhase("login");
        }
      } catch {
        if (!cancelled) setPhase("offline");
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- boot once
  }, []);

  function navigate(href: string) {
    setRoute(href);
    const p = parseRoute(href);
    if (p.patientId) setPatientViewId(p.patientId);
    else if (p.base !== "/patients") setPatientViewId(null);
    if (p.encounterId) setEncounterViewId(p.encounterId);
    else if (p.base !== "/encounters") setEncounterViewId(null);
  }

  function clearPatientScopedUi() {
    setPatientViewId(null);
    setEncounterViewId(null);
    setRoute("/");
  }

  async function onLogin(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    setLogoutNote(null);
    try {
      const body = await nativeLogin(email.trim(), password);
      session.setProfile(body);
      setPassword("");
      if (body.tenants.length === 1) {
        await session.selectTenant(body.tenants[0]);
        setPhase("ready");
      } else if (body.tenants.length === 0) {
        setPhase("ready");
      } else {
        setPhase("workspace");
      }
    } catch {
      setError("Sign-in failed. Check your email and password.");
      setPhase("login");
    } finally {
      setBusy(false);
    }
  }

  async function onLogout() {
    setBusy(true);
    try {
      const result = await nativeLogout();
      setLogoutNote(
        result.backendOk
          ? null
          : "Signed out locally; server logout may have been unreachable.",
      );
    } finally {
      session.reset();
      clearPatientScopedUi();
      setBusy(false);
      setPhase("login");
    }
  }

  function onSessionExpired() {
    session.reset();
    clearPatientScopedUi();
    setPhase("session_expired");
  }

  function renderModule() {
    const base = parsed.base;
    const openPatientId = parsed.patientId ?? patientViewId;
    const openEncounterId = parsed.encounterId ?? encounterViewId;

    if (base === "/") {
      return <Dashboard onSessionExpired={onSessionExpired} />;
    }

    if (base === "/patients") {
      if (openPatientId) {
        return (
          <PatientProfile
            patientId={openPatientId}
            onBack={() => {
              setPatientViewId(null);
              setRoute("/patients");
            }}
            onBook={(id) => navigate(`/schedule?patient=${encodeURIComponent(id)}`)}
            onConsult={(id) =>
              navigate(`/encounters?patient=${encodeURIComponent(id)}`)
            }
            onOpenBilling={(patientId, tab) =>
              navigate(
                `/billing/invoices?patient=${encodeURIComponent(patientId)}${tab ? `&tab=${tab}` : ""}`,
              )
            }
            onOpenTreatmentPlans={(id) =>
              navigate(`/dental/plans?patient=${encodeURIComponent(id)}`)
            }
            onSessionExpired={onSessionExpired}
          />
        );
      }
      return (
        <PatientsDirectory
          onOpenPatient={(id) => {
            setPatientViewId(id);
            setRoute(`/patients/${id}`);
          }}
          onSessionExpired={onSessionExpired}
        />
      );
    }

    if (base === "/billing/invoices") {
      return (
        <BillingHub
          initialTab={parsed.billingTab ?? "invoices"}
          initialEstimateId={parsed.queryEstimate}
          initialInvoiceId={parsed.queryInvoice}
          initialPatientId={parsed.queryPatient}
          onOpenPatient={(id) => {
            setPatientViewId(id);
            setRoute(`/patients/${id}`);
          }}
          onSessionExpired={onSessionExpired}
        />
      );
    }

    if (base === "/dental/plans") {
      return (
        <TreatmentPlansHub
          initialPatientId={parsed.queryPatient}
          onOpenPatient={(id) => {
            setPatientViewId(id);
            setRoute(`/patients/${id}`);
          }}
          onSessionExpired={onSessionExpired}
        />
      );
    }

    if (base === "/schedule") {
      return (
        <ScheduleCalendar
          initialPatientId={parsed.queryPatient}
          onOpenPatient={(id) => {
            setPatientViewId(id);
            setRoute(`/patients/${id}`);
          }}
          onConsult={(appointmentId, patientId) =>
            navigate(
              `/encounters?appointment=${encodeURIComponent(appointmentId)}&patient=${encodeURIComponent(patientId)}`,
            )
          }
          onSessionExpired={onSessionExpired}
        />
      );
    }

    if (base === "/staff") {
      return <StaffHub onSessionExpired={onSessionExpired} />;
    }

    if (base === "/reception") {
      return (
        <ReceptionQueue
          onOpenPatient={(id) => {
            setPatientViewId(id);
            setRoute(`/patients/${id}`);
          }}
          onRegisterHandoff={() => navigate("/patients")}
          onConsult={(appointmentId, patientId) =>
            navigate(
              `/encounters?appointment=${encodeURIComponent(appointmentId)}&patient=${encodeURIComponent(patientId)}`,
            )
          }
          onSessionExpired={onSessionExpired}
        />
      );
    }

    if (base === "/encounters") {
      if (openEncounterId) {
        return (
          <EncounterWorkspace
            encounterId={openEncounterId}
            onBack={() => {
              setEncounterViewId(null);
              setRoute("/encounters");
            }}
            onOpenPatient={(id) => {
              setPatientViewId(id);
              setRoute(`/patients/${id}`);
            }}
            onSessionExpired={onSessionExpired}
          />
        );
      }
      return (
        <DoctorConsultBoard
          initialPatientId={parsed.queryPatient}
          initialAppointmentId={parsed.queryAppointment}
          onOpenEncounter={(id) => {
            setEncounterViewId(id);
            setRoute(`/encounters/${id}`);
          }}
          onOpenPatient={(id) => {
            setPatientViewId(id);
            setRoute(`/patients/${id}`);
          }}
          onSessionExpired={onSessionExpired}
        />
      );
    }

    return <ModulePlaceholder title={base.replace(/^\//, "")} />;
  }

  if (phase === "booting") {
    return (
      <main className="hos-desktop-root">
        <LoadingState label="Starting Healthcare OS" />
      </main>
    );
  }

  if (phase === "offline") {
    return (
      <main className="hos-desktop-root hos-desktop-center">
        <ErrorState title="Cannot reach API" onRetry={() => window.location.reload()}>
          {`Channel: ${channel}. No response from ${apiBase || "configured API"}.`}
        </ErrorState>
      </main>
    );
  }

  if (phase === "session_expired") {
    return (
      <main className="hos-desktop-root hos-desktop-center">
        <Card title="Session expired" headingLevel={1}>
          <p>Sign in again to continue.</p>
          <Button type="button" onClick={() => setPhase("login")}>
            Return to sign-in
          </Button>
        </Card>
      </main>
    );
  }

  if (phase === "login") {
    return (
      <main className="hos-desktop-root hos-desktop-center">
        <Card title="Clinic sign-in" headingLevel={1}>
          <p className="hos-desktop-brand">Healthcare OS</p>
          <p className="hos-muted">
            Online clinic workstation · channel {channel}
          </p>
          {logoutNote && <Alert tone="warning" title="Notice">{logoutNote}</Alert>}
          {error && (
            <Alert tone="danger" title="Sign-in error">
              {error}
            </Alert>
          )}
          <form onSubmit={onLogin} data-testid="login-form">
            <Field label="Email" htmlFor="email" required>
              {({ describedBy }) => (
                <Input
                  id="email"
                  name="email"
                  type="email"
                  autoComplete="username"
                  aria-describedby={describedBy}
                  value={email}
                  onChange={(ev) => setEmail(ev.target.value)}
                  required
                />
              )}
            </Field>
            <Field label="Password" htmlFor="password" required>
              {({ describedBy }) => (
                <Input
                  id="password"
                  name="password"
                  type="password"
                  autoComplete="current-password"
                  aria-describedby={describedBy}
                  value={password}
                  onChange={(ev) => setPassword(ev.target.value)}
                  required
                />
              )}
            </Field>
            <Button type="submit" disabled={busy} loading={busy}>
              Sign in
            </Button>
          </form>
          <p className="hos-caption">
            API: {apiBase} · access in memory: {getAccessToken() ? "yes" : "no"}
          </p>
        </Card>
      </main>
    );
  }

  if (phase === "workspace" && session.profile) {
    return (
      <main className="hos-desktop-root hos-desktop-center">
        <Card title="Select clinic" headingLevel={1}>
          <p>Signed in as {session.profile.display_name}</p>
          {session.profile.tenants.map((t) => (
            <Button
              key={t.id}
              type="button"
              onClick={async () => {
                setBusy(true);
                try {
                  clearPatientScopedUi();
                  await session.selectTenant(t);
                  setPhase("ready");
                } catch {
                  setError("Could not authorize that clinic.");
                } finally {
                  setBusy(false);
                }
              }}
            >
              {t.name} ({t.slug})
            </Button>
          ))}
        </Card>
      </main>
    );
  }

  return (
    <Shell
      route={
        parsed.base === "/patients" && patientViewId
          ? `/patients/${patientViewId}`
          : parsed.base === "/encounters" && encounterViewId
            ? `/encounters/${encounterViewId}`
            : parsed.base
      }
      onNavigate={(href) => {
        if (href === "/patients") setPatientViewId(null);
        if (href === "/encounters") setEncounterViewId(null);
        navigate(href);
      }}
      onLogout={onLogout}
      onSwitchWorkspace={() => {
        clearPatientScopedUi();
        session.clearTenantScoped();
        setPhase("workspace");
      }}
      onSessionExpired={onSessionExpired}
    >
      {renderModule()}
    </Shell>
  );
}

export default function App() {
  return (
    <SessionProvider>
      <AppInner />
    </SessionProvider>
  );
}
