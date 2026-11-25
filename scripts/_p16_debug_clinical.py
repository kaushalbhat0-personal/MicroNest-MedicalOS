import httpx

BASE = "http://localhost:8000"
c = httpx.Client(timeout=30)
r = c.post(
    f"{BASE}/api/v1/auth/native/login",
    json={
        "email": "desktop.poc@example.com",
        "password": "Desktop-PoC-Only-99zz",
        "client_platform": "windows",
        "device_label": "x",
        "client_instance_id": "dbg",
    },
)
b = r.json()
t = b["access_token"]
tid = b["tenants"][0]["id"]
h = {"Authorization": f"Bearer {t}", "X-Tenant": tid}
locs = c.get(f"{BASE}/api/v1/tenants/{tid}/locations", headers=h).json()
pracs = c.get(f"{BASE}/api/v1/tenants/{tid}/practitioners", headers=h).json()
ap = [p for p in pracs if p.get("verification_status") == "approved"]
print("pracs", [(p["display_name"], p.get("verification_status")) for p in pracs])
loc = locs[0]["id"]
prac = ap[0]["id"]
pat = c.post(
    f"{BASE}/api/v1/tenants/{tid}/patients",
    headers=h,
    json={"display_name": "NoteDbg"},
).json()
enc = c.post(
    f"{BASE}/api/v1/tenants/{tid}/encounters",
    headers=h,
    json={
        "patient_id": pat["id"],
        "practitioner_id": prac,
        "location_id": loc,
    },
).json()
print("enc", enc["id"], enc["status"], "prac", enc["practitioner_id"])
note = c.post(
    f"{BASE}/api/v1/tenants/{tid}/encounters/{enc['id']}/clinical-notes",
    headers=h,
    json={"subjective": "hi", "objective": "obj"},
)
print("note", note.status_code, note.text[:500])
otypes = c.get(f"{BASE}/api/v1/tenants/{tid}/observation-types", headers=h)
print("otypes", otypes.status_code, otypes.text[:400])
meds = c.get(f"{BASE}/api/v1/tenants/{tid}/medications", headers=h)
print("meds", meds.status_code, len(meds.json()) if meds.status_code == 200 else meds.text[:200])
if meds.status_code == 200 and meds.json():
    code = meds.json()[0]["code"]
    rx = c.post(
        f"{BASE}/api/v1/tenants/{tid}/encounters/{enc['id']}/prescriptions",
        headers=h,
        json={
            "items": [
                {
                    "medication_code": code,
                    "dose": "1 tablet",
                    "route": "oral",
                    "frequency": "once daily",
                    "duration_days": 5,
                    "instructions": "synthetic",
                }
            ]
        },
    )
    print("rx", rx.status_code, rx.text[:400])
plan = c.post(
    f"{BASE}/api/v1/tenants/{tid}/treatment-plans",
    headers=h,
    json={
        "patient_id": pat["id"],
        "encounter_id": enc["id"],
        "notes": "x",
        "items": [{"procedure_code": "D0150", "sequence": 1}],
    },
)
print("plan", plan.status_code, plan.text[:400])
wc = c.get(f"{BASE}/api/v1/tenants/{tid}/workspace-context", headers=h).json()
for p in [
    "clinical.create",
    "prescription.create",
    "prescription.sign",
    "plan.manage",
    "dental.record",
]:
    print(p, p in wc.get("permissions", []))
