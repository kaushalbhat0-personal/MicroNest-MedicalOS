import { useEffect, useState } from "react";
import patients from "../../fixtures/assigned-patients.json";

const API = import.meta.env.VITE_POC_API_URL || "http://127.0.0.1:8787";

type Session = { email: string; displayName: string };

/** In-memory only for browser PoC. On device: Keystore-backed secure store. */
let memoryToken: string | null = null;

async function login(email: string, password: string): Promise<Session> {
  const r = await fetch(`${API}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!r.ok) throw new Error("login_failed");
  const data = await r.json();
  memoryToken = data.access_token;
  // Never log access_token
  return { email: data.email, displayName: data.display_name };
}

async function me(): Promise<Session> {
  const r = await fetch(`${API}/api/v1/auth/me`, {
    headers: { Authorization: `Bearer ${memoryToken}` },
  });
  if (!r.ok) throw new Error("me_failed");
  const data = await r.json();
  return { email: data.email, displayName: data.display_name };
}

async function logout(): Promise<void> {
  try {
    await fetch(`${API}/api/v1/auth/logout`, {
      method: "POST",
      headers: { Authorization: `Bearer ${memoryToken}` },
    });
  } finally {
    memoryToken = null;
  }
}

export function App() {
  const [online, setOnline] = useState(navigator.onLine);
  const [session, setSession] = useState<Session | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [email, setEmail] = useState("poc.owner@example.com");
  const [password, setPassword] = useState("PoC-Only-Not-A-Secret-99");

  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);

  return (
    <main style={{ fontFamily: "system-ui", padding: 24, maxWidth: 480 }}>
      <h1>Healthcare OS — Android SPA PoC</h1>
      <p>Network: {online ? "online" : "offline"}</p>
      {error && <p role="alert">{error}</p>}
      {!session ? (
        <form
          onSubmit={async (e) => {
            e.preventDefault();
            setError(null);
            try {
              await login(email, password);
              setSession(await me());
            } catch {
              setError("Authentication failed (token not logged).");
            }
          }}
        >
          <label>
            Email
            <input value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button type="submit">Login</button>
        </form>
      ) : (
        <div>
          <p>Signed in as {session.displayName}</p>
          <button
            type="button"
            onClick={async () => {
              await logout();
              setSession(null);
            }}
          >
            Logout
          </button>
        </div>
      )}
      <section>
        <h2>Assigned patients (synthetic offline fixture)</h2>
        <ul>
          {patients.patients.map((p) => (
            <li key={p.id}>
              {p.display_name} — {p.mrn}
            </li>
          ))}
        </ul>
      </section>
      <p style={{ fontSize: 12, opacity: 0.7 }}>
        Keystore + SQLCipher: see native/kotlin samples — NOT runtime-proven in this SPA shell alone.
      </p>
    </main>
  );
}
