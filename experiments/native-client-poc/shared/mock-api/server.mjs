/**
 * Controlled test backend for A1/A2 PoCs — NOT the production FastAPI app.
 * Issues synthetic Bearer tokens only. No PHI. No real credentials.
 */
import http from "node:http";
import { randomBytes, createHmac } from "node:crypto";

const PORT = Number(process.env.POC_MOCK_API_PORT || 8787);
const SECRET = randomBytes(32); // ephemeral process secret
const sessions = new Map(); // token -> { email, exp }

const SYN_USER = {
  id: "00000000-0000-4000-8000-000000000001",
  email: "poc.owner@example.com",
  display_name: "PoC Synthetic Owner",
  tenants: [{ id: "00000000-0000-4000-8000-0000000000aa", slug: "poc-clinic", name: "PoC Clinic" }],
};

function json(res, status, body) {
  const data = JSON.stringify(body);
  res.writeHead(status, {
    "Content-Type": "application/json",
    "Cache-Control": "no-store",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Authorization, Content-Type, X-Tenant",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
  });
  res.end(data);
}

function mintToken(email) {
  const token = createHmac("sha256", SECRET).update(email + randomBytes(8)).digest("hex");
  sessions.set(token, { email, exp: Date.now() + 15 * 60_000 });
  return token;
}

function auth(req) {
  const h = req.headers.authorization || "";
  if (!h.startsWith("Bearer ")) return null;
  const token = h.slice(7);
  const s = sessions.get(token);
  if (!s || s.exp < Date.now()) return null;
  return s;
}

const server = http.createServer(async (req, res) => {
  if (req.method === "OPTIONS") {
    return json(res, 204, {});
  }
  const url = new URL(req.url || "/", `http://127.0.0.1:${PORT}`);

  if (req.method === "POST" && url.pathname === "/api/v1/auth/login") {
    const chunks = [];
    for await (const c of req) chunks.push(c);
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8") || "{}");
    // Accept only the synthetic PoC account
    if (body.email !== SYN_USER.email || body.password !== "PoC-Only-Not-A-Secret-99") {
      return json(res, 401, { detail: "invalid credentials" });
    }
    const access_token = mintToken(body.email);
    return json(res, 200, {
      ...SYN_USER,
      access_token,
      token_type: "bearer",
      expires_in: 900,
      note: "PoC mock only — production FastAPI currently sets HttpOnly cookies",
    });
  }

  if (req.method === "GET" && url.pathname === "/api/v1/auth/me") {
    const s = auth(req);
    if (!s) return json(res, 401, { detail: "authentication required" });
    return json(res, 200, SYN_USER);
  }

  if (req.method === "POST" && url.pathname === "/api/v1/auth/logout") {
    const h = req.headers.authorization || "";
    if (h.startsWith("Bearer ")) sessions.delete(h.slice(7));
    return json(res, 204, {});
  }

  if (req.method === "GET" && url.pathname === "/api/healthz") {
    return json(res, 200, { status: "ok", service: "poc-mock-api" });
  }

  return json(res, 404, { detail: "not found" });
});

server.listen(PORT, "127.0.0.1", () => {
  console.log(`poc_mock_api_listening=127.0.0.1:${PORT}`);
});
