"""Same-site API probes for tenant isolation + cookie presence. No secrets printed."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(p: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip().strip('"').strip("'")
    return out


class Ctx:
    def __init__(self, api: str) -> None:
        self.api = api
        self.jar = CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def post(self, path: str, body: dict) -> tuple[int, object]:
        req = urllib.request.Request(
            self.api + path,
            data=json.dumps(body).encode(),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.op.open(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode())

    def get(self, path: str, headers: dict[str, str] | None = None) -> tuple[int, object]:
        req = urllib.request.Request(self.api + path, headers=headers or {})
        try:
            with self.op.open(req, timeout=60) as resp:
                return resp.status, json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            body = exc.read().decode(errors="replace")[:200]
            try:
                return exc.code, json.loads(body)
            except json.JSONDecodeError:
                return exc.code, body


def main() -> int:
    st = load(ROOT / ".env.p37c.staging")
    api = st.get("P37C_API_BASE") or "https://micronest-medicalos.onrender.com"
    a = Ctx(api)
    st_a, me_a = a.post(
        "/api/v1/auth/login",
        {"email": st["P37C_OWNER_A_EMAIL"], "password": st["P37C_OWNER_A_PASSWORD"]},
    )
    assert isinstance(me_a, dict)
    tid_a = (me_a.get("tenants") or [{}])[0].get("id")
    print(f"login_A={st_a} tenants={len(me_a.get('tenants') or [])} tid_a={bool(tid_a)}")
    print(f"cookie_names_A={[c.name for c in a.jar]}")

    sa, patients_a = a.get(f"/api/v1/tenants/{tid_a}/patients", {"X-Tenant": str(tid_a)})
    print(f"list_A={sa} count={len(patients_a) if isinstance(patients_a, list) else type(patients_a).__name__}")

    b = Ctx(api)
    st_b, me_b = b.post(
        "/api/v1/auth/login",
        {"email": st["P37C_OWNER_B_EMAIL"], "password": st["P37C_OWNER_B_PASSWORD"]},
    )
    assert isinstance(me_b, dict)
    tid_b = (me_b.get("tenants") or [{}])[0].get("id")
    print(f"login_B={st_b} tid_b={bool(tid_b)}")
    sb, patients_b = b.get(f"/api/v1/tenants/{tid_b}/patients", {"X-Tenant": str(tid_b)})
    print(f"list_B={sb} count={len(patients_b) if isinstance(patients_b, list) else type(patients_b).__name__}")

    if isinstance(patients_b, list) and patients_b:
        other = patients_b[0].get("id")
        sc, _ = a.get(f"/api/v1/tenants/{tid_a}/patients/{other}", {"X-Tenant": str(tid_a)})
        print(f"cross_A_reads_B_id_under_A_tenant={sc}")
        sc2, _ = a.get(f"/api/v1/tenants/{tid_b}/patients/{other}", {"X-Tenant": str(tid_b)})
        print(f"cross_A_reads_B_tenant_scope={sc2}")
        denied = sc in (403, 404) and sc2 in (403, 404)
        print(f"cross_tenant_denied={denied}")
    else:
        print("cross_tenant_denied=SKIP no_patients_B")

    r = Ctx(api)
    sr, me_r = r.post(
        "/api/v1/auth/login",
        {"email": st["P37C_RECV_A_EMAIL"], "password": st["P37C_RECV_A_PASSWORD"]},
    )
    blob = json.dumps(me_r).lower()
    print(f"recv_login={sr} staff_manage={'staff.manage' in blob}")

    p = Ctx(api)
    sp, me_p = p.post(
        "/api/v1/auth/login",
        {"email": st["P37C_PORTAL_A1_EMAIL"], "password": st["P37C_PORTAL_A1_PASSWORD"]},
    )
    print(f"portal_login={sp} tenants={len((me_p or {}).get('tenants') or []) if isinstance(me_p, dict) else 0}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
