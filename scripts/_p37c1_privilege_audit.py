"""P3.7C.1 staging privilege / RLS audit. Never prints secrets."""
from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import quote_plus, urlparse, urlunparse

from sqlalchemy import create_engine, text

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "_p37c1_privilege_audit.json"


def load(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, v = s.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def as_role(url: str, role: str) -> str:
    p = urlparse(url)
    user = p.username or ""
    if "." not in user:
        raise RuntimeError("expected pooler username role.project_ref")
    _, ref = user.split(".", 1)
    new_user = f"{role}.{ref}"
    password = p.password or ""
    host = p.hostname or ""
    port = f":{p.port}" if p.port else ""
    netloc = f"{quote_plus(new_user)}:{quote_plus(password)}@{host}{port}"
    return urlunparse((p.scheme, netloc, p.path, p.params, p.query, p.fragment))


def shape(url: str) -> dict[str, str | None]:
    p = urlparse(url)
    return {
        "user": p.username,
        "host": p.hostname,
        "db": (p.path or "").lstrip("/"),
        "sslmode": dict(
            kv.split("=", 1) for kv in (p.query or "").split("&") if "=" in kv
        ).get("sslmode"),
    }


def main() -> int:
    env = load(ROOT / ".env")
    owner_url = env["OWNER_DATABASE_URL_CLOUD"]
    app_url = env["APP_DATABASE_URL_CLOUD"]
    pg_url = as_role(owner_url, "postgres")

    report: dict = {
        "db_identity": {
            "owner_url_shape": shape(owner_url),
            "app_url_shape": shape(app_url),
            "postgres_url_shape": shape(pg_url),
        },
        "roles": {},
        "schema": {},
        "rls": {},
        "seed_roles": {},
        "security_definer": [],
        "default_privileges": [],
        "hos_app_checks": {},
        "hos_owner_checks": {},
    }

    # --- Role attributes via postgres ---
    peng = create_engine(pg_url, pool_pre_ping=True)
    with peng.connect() as c:
        report["db_identity"]["current_database"] = c.execute(
            text("SELECT current_database()")
        ).scalar()
        report["db_identity"]["alembic_revision"] = c.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
        rows = c.execute(
            text(
                """
                SELECT rolname, rolsuper, rolbypassrls, rolcreatedb, rolcreaterole,
                       rolcanlogin, rolinherit
                FROM pg_roles
                WHERE rolname IN ('postgres','hos_owner','hos_app','authenticator','anon','authenticated')
                ORDER BY rolname
                """
            )
        ).mappings().all()
        for r in rows:
            report["roles"][r["rolname"]] = dict(r)

        # memberships
        mem = c.execute(
            text(
                """
                SELECT r.rolname AS role, m.rolname AS member_of
                FROM pg_auth_members am
                JOIN pg_roles r ON r.oid = am.member
                JOIN pg_roles m ON m.oid = am.roleid
                WHERE r.rolname IN ('hos_owner','hos_app','postgres')
                ORDER BY 1,2
                """
            )
        ).all()
        report["role_memberships"] = [{"role": a, "member_of": b} for a, b in mem]

        # table ownership sample + grants
        owners = c.execute(
            text(
                """
                SELECT tableowner, count(*) AS n
                FROM pg_tables WHERE schemaname='public'
                GROUP BY 1 ORDER BY 2 DESC
                """
            )
        ).all()
        report["schema"]["table_owners"] = [{"owner": o, "count": n} for o, n in owners]
        report["schema"]["public_table_count"] = c.execute(
            text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE'"
            )
        ).scalar()

        # privileges on key tables
        priv = c.execute(
            text(
                """
                SELECT grantee, table_name, string_agg(privilege_type, ',' ORDER BY privilege_type) AS privs
                FROM information_schema.role_table_grants
                WHERE table_schema='public'
                  AND grantee IN ('hos_app','hos_owner','PUBLIC')
                  AND table_name IN (
                    'tenants','patients','roles','memberships','estimates','invoices',
                    'payments','alembic_version','treatment_plans'
                  )
                GROUP BY 1,2
                ORDER BY 1,2
                """
            )
        ).all()
        report["schema"]["key_table_grants"] = [
            {"grantee": g, "table": t, "privileges": p} for g, t, p in priv
        ]

        # RLS / FORCE
        rls = c.execute(
            text(
                """
                SELECT c.relname,
                       c.relrowsecurity AS rls,
                       c.relforcerowsecurity AS force_rls
                FROM pg_class c
                JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE n.nspname='public' AND c.relkind='r'
                ORDER BY 1
                """
            )
        ).all()
        report["rls"]["tables"] = [
            {"table": name, "rls": bool(rls_on), "force_rls": bool(force)}
            for name, rls_on, force in rls
        ]
        report["rls"]["force_enabled_count"] = sum(1 for _, _, f in rls if f)
        report["rls"]["rls_enabled_count"] = sum(1 for _, r, _ in rls if r)

        # seed roles
        seeds = c.execute(
            text(
                """
                SELECT name, jsonb_array_length(permissions) AS n,
                       permissions ? 'patient.create' AS has_patient_create,
                       permissions ? 'plan.manage' AS has_plan_manage,
                       permissions ? 'invoice.issue' AS has_invoice_issue,
                       permissions ? 'payment.record' AS has_payment_record,
                       permissions ? 'billing.refund' AS has_billing_refund,
                       permissions ? 'refund.create' AS has_bogus_refund_create,
                       permissions
                FROM roles
                WHERE tenant_id IS NULL
                ORDER BY name
                """
            )
        ).mappings().all()
        for s in seeds:
            perms = s["permissions"]
            report["seed_roles"][s["name"]] = {
                "permission_count": s["n"],
                "has_patient_create": s["has_patient_create"],
                "has_plan_manage": s["has_plan_manage"],
                "has_invoice_issue": s["has_invoice_issue"],
                "has_payment_record": s["has_payment_record"],
                "has_billing_refund": s["has_billing_refund"],
                "has_bogus_refund_create": s["has_bogus_refund_create"],
                "permissions": sorted(perms),
            }

        # SECURITY DEFINER functions in public
        sdf = c.execute(
            text(
                """
                SELECT p.proname, pg_get_userbyid(p.proowner) AS owner,
                       p.prosecdef AS security_definer,
                       coalesce(p.proconfig::text,'') AS config
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid=p.pronamespace
                WHERE n.nspname='public' AND p.prosecdef = true
                ORDER BY 1
                """
            )
        ).all()
        report["security_definer"] = [
            {"name": n, "owner": o, "security_definer": True, "config": cfg}
            for n, o, _, cfg in sdf
        ]

        # default ACLs
        dacl = c.execute(
            text(
                """
                SELECT pg_get_userbyid(d.defaclrole) AS role_name,
                       n.nspname AS schema,
                       d.defaclobjtype AS objtype,
                       d.defaclacl::text AS acl
                FROM pg_default_acl d
                LEFT JOIN pg_namespace n ON n.oid = d.defaclnamespace
                ORDER BY 1,2
                """
            )
        ).all()
        report["default_privileges"] = [
            {"role": r, "schema": s, "objtype": o, "acl": a} for r, s, o, a in dacl
        ]

        # schema usage
        report["schema"]["hos_app_usage"] = c.execute(
            text(
                """
                SELECT has_schema_privilege('hos_app','public','USAGE') AS usage,
                       has_schema_privilege('hos_app','public','CREATE') AS create
                """
            )
        ).mappings().first()
        report["schema"]["hos_owner_usage"] = c.execute(
            text(
                """
                SELECT has_schema_privilege('hos_owner','public','USAGE') AS usage,
                       has_schema_privilege('hos_owner','public','CREATE') AS create
                """
            )
        ).mappings().first()

    # --- hos_app least privilege probes ---
    aeng = create_engine(app_url, pool_pre_ping=True)
    with aeng.connect() as c:
        report["hos_app_checks"]["current_user"] = c.execute(
            text("SELECT current_user")
        ).scalar()
        report["hos_app_checks"]["bypassrls"] = c.execute(
            text("SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user")
        ).scalar()
        # DDL
        try:
            c.execute(text("CREATE TABLE p37c1_ddl_probe(id int)"))
            c.commit()
            report["hos_app_checks"]["ddl_create_table"] = "FAIL_ALLOWED"
        except Exception as exc:
            c.rollback()
            report["hos_app_checks"]["ddl_create_table"] = f"DENIED:{type(exc).__name__}"
        # alembic write
        try:
            c.execute(
                text(
                    "UPDATE alembic_version SET version_num = 'p37c1_should_fail' "
                    "WHERE version_num IS NOT NULL"
                )
            )
            c.commit()
            report["hos_app_checks"]["alembic_update"] = "FAIL_ALLOWED"
            # try restore if somehow allowed
            c.execute(
                text(
                    "UPDATE alembic_version SET version_num = '0027_saas_payment_reliability'"
                )
            )
            c.commit()
        except Exception as exc:
            c.rollback()
            report["hos_app_checks"]["alembic_update"] = f"DENIED:{type(exc).__name__}"
        try:
            c.execute(text("SELECT version_num FROM alembic_version")).scalar()
            report["hos_app_checks"]["alembic_select"] = "ALLOWED"
        except Exception as exc:
            c.rollback()
            report["hos_app_checks"]["alembic_select"] = f"DENIED:{type(exc).__name__}"
        # RLS without tenant
        locs = c.execute(text("SELECT count(*) FROM locations")).scalar()
        patients = c.execute(text("SELECT count(*) FROM patients")).scalar()
        report["hos_app_checks"]["locations_without_tenant"] = locs
        report["hos_app_checks"]["patients_without_tenant"] = patients

    # --- hos_owner probes ---
    oeng = create_engine(owner_url, pool_pre_ping=True)
    with oeng.connect() as c:
        report["hos_owner_checks"]["current_user"] = c.execute(
            text("SELECT current_user")
        ).scalar()
        report["hos_owner_checks"]["bypassrls"] = c.execute(
            text("SELECT rolbypassrls FROM pg_roles WHERE rolname=current_user")
        ).scalar()
        # can see seed roles now?
        n = c.execute(
            text("SELECT count(*) FROM roles WHERE tenant_id IS NULL")
        ).scalar()
        report["hos_owner_checks"]["seed_roles_visible"] = n
        # can update seed role (migration pattern)?
        try:
            res = c.execute(
                text(
                    "UPDATE roles SET permissions = permissions "
                    "WHERE tenant_id IS NULL AND name = 'staff'"
                )
            )
            c.commit()
            report["hos_owner_checks"]["seed_role_update_rowcount"] = res.rowcount
        except Exception as exc:
            c.rollback()
            report["hos_owner_checks"]["seed_role_update"] = f"DENIED:{type(exc).__name__}"

    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"wrote {OUT.name}")
    print(f"alembic={report['db_identity']['alembic_revision']}")
    for name, attrs in report["roles"].items():
        print(
            f"role {name}: super={attrs['rolsuper']} bypassrls={attrs['rolbypassrls']} "
            f"createdb={attrs['rolcreatedb']} createrole={attrs['rolcreaterole']} "
            f"login={attrs['rolcanlogin']}"
        )
    ta = report["seed_roles"].get("tenant_admin", {})
    print(
        f"tenant_admin n={ta.get('permission_count')} "
        f"patient.create={ta.get('has_patient_create')} "
        f"plan.manage={ta.get('has_plan_manage')} "
        f"bogus_refund.create={ta.get('has_bogus_refund_create')}"
    )
    print(f"hos_app ddl={report['hos_app_checks']['ddl_create_table']}")
    print(f"hos_app alembic_update={report['hos_app_checks']['alembic_update']}")
    print(
        f"hos_app locations_wo_tenant={report['hos_app_checks']['locations_without_tenant']} "
        f"patients_wo_tenant={report['hos_app_checks']['patients_without_tenant']}"
    )
    print(
        f"hos_owner bypass={report['hos_owner_checks']['bypassrls']} "
        f"seed_visible={report['hos_owner_checks']['seed_roles_visible']} "
        f"seed_update_rowcount={report['hos_owner_checks'].get('seed_role_update_rowcount')}"
    )
    print(f"security_definer_count={len(report['security_definer'])}")
    print(f"force_rls_tables={report['rls']['force_enabled_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
