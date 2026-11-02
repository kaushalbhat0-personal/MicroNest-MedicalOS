"""Local PostgreSQL for dev/test when Docker registry is unreachable.

Uses real PostgreSQL binaries (via the `pgserver` package) — never SQLite.
Data lives under ./var/pgdata (gitignored).

Usage:
  python infrastructure/dev/local_pg.py init    # one-time cluster + roles + DBs
  python infrastructure/dev/local_pg.py start   # start on 127.0.0.1:5432
  python infrastructure/dev/local_pg.py stop
  python infrastructure/dev/local_pg.py status
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VAR = ROOT / "var"
PGDATA = VAR / "pgdata"
LOGFILE = PGDATA / "log"
PORT = "5432"

OWNER = "hos_owner"
OWNER_PW = os.environ.get("LOCAL_PG_OWNER_PW", "owner-dev-pass")
APP_PW = os.environ.get("LOCAL_PG_APP_PW", "change-me-app-role")


def _pg() -> object:
    sys.path.insert(0, str(ROOT / "backend"))
    import pgserver  # type: ignore[import]

    return pgserver


def cmd_init() -> None:
    pg = _pg()
    VAR.mkdir(exist_ok=True)
    if not (PGDATA / "PG_VERSION").exists():
        print(f"initdb {PGDATA}")
        pg.initdb(["-U", OWNER, "-E", "UTF8", "--auth=trust"], pgdata=PGDATA)
    cmd_start()
    import psycopg2  # type: ignore[import]

    conn = psycopg2.connect(
        host="127.0.0.1", port=PORT, user=OWNER, dbname="postgres"
    )
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='hos_app') "
        "THEN CREATE ROLE hos_app LOGIN; END IF; END $$;"
    )
    cur.execute("ALTER ROLE hos_owner WITH PASSWORD %s", (OWNER_PW,))
    cur.execute("ALTER ROLE hos_app WITH PASSWORD %s", (APP_PW,))
    for dbname in ("healthcare_os", "healthcare_os_test"):
        cur.execute("SELECT 1 FROM pg_database WHERE datname=%s", (dbname,))
        if cur.fetchone() is None:
            cur.execute(f'CREATE DATABASE "{dbname}" OWNER hos_owner')
            print(f"created database {dbname}")
    conn.close()
    print("local postgres initialized")


def cmd_start() -> None:
    pg = _pg()
    LOGFILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        pg.pg_ctl(
            ["-o", f"-p {PORT} -c listen_addresses=127.0.0.1", "-l", str(LOGFILE), "start"],
            pgdata=PGDATA,
        )
    except subprocess.CalledProcessError as exc:
        print(f"pg_ctl start issue (may already run): {exc}")
    print("local postgres started on 127.0.0.1:5432")


def cmd_stop() -> None:
    pg = _pg()
    pg.pg_ctl(["stop", "-m", "fast"], pgdata=PGDATA)
    print("local postgres stopped")


def cmd_status() -> None:
    pg = _pg()
    print(pg.pg_isready(["-h", "127.0.0.1", "-p", PORT], pgdata=None))


def main(argv: list[str]) -> int:
    cmd = argv[1] if len(argv) > 1 else "status"
    if cmd == "init":
        cmd_init()
    elif cmd == "start":
        cmd_start()
    elif cmd == "stop":
        cmd_stop()
    else:
        cmd_status()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
