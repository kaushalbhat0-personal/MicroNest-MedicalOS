from pathlib import Path

from sqlalchemy import create_engine, text

env: dict[str, str] = {}
for line in Path(".env").read_text(encoding="utf-8").splitlines():
    s = line.strip()
    if s and not s.startswith("#") and "=" in s:
        k, v = s.split("=", 1)
        env[k.strip()] = v.strip()

for label, url in (
    ("local", env["OWNER_DATABASE_URL"]),
    ("cloud", env["OWNER_DATABASE_URL_CLOUD"]),
):
    eng = create_engine(url, pool_pre_ping=True)
    with eng.connect() as c:
        r = c.execute(
            text(
                "select current_user, rolbypassrls, rolsuper "
                "from pg_roles where rolname=current_user"
            )
        ).one()
        print(label, "user", r[0], "bypass", r[1], "super", r[2])
