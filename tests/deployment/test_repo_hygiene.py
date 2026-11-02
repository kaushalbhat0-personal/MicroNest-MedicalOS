"""Repository hygiene: no secrets in git, no auth tokens in browser storage."""

import pathlib
import re
import shutil
import subprocess

import pytest


def _tracked_files() -> list[str] | None:
    if shutil.which("git") is None:
        return None
    try:
        out = subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True, timeout=30, check=True
        ).stdout.splitlines()
        return out
    except Exception:  # noqa: BLE001 — not a git repo (or no commits): fall through
        return None


def test_no_secret_files_tracked() -> None:
    tracked = _tracked_files()
    if tracked is None:
        pytest.skip("not a git repository")
    bad = [
        f
        for f in tracked
        if f == ".env"
        or f.endswith(".pem")
        or f.endswith(".key")
        or f.endswith(".p12")
        or "/.env" in f
        or f.startswith("_ref_")
    ]
    assert bad == [], f"secret/reference files tracked: {bad}"


def test_env_example_is_placeholder_only() -> None:
    example = pathlib.Path(".env.example").read_text()
    assert "change-me" in example, "example must use placeholder secrets"
    assert "OWNER_DATABASE_URL=" in example


def test_env_is_gitignored() -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available")
    for path in (".env", "var/storage/x"):
        proc = subprocess.run(
            ["git", "check-ignore", "-q", path],
            capture_output=True,
            timeout=30,
        )
        assert proc.returncode == 0, f"{path} must be gitignored"


def test_no_tokens_in_browser_storage() -> None:
    """Auth tokens must never touch localStorage/sessionStorage (HttpOnly
    cookies only). The tenant selector (non-secret) is explicitly allowed."""
    tokenish = re.compile(
        r"(localStorage|sessionStorage)\s*[\.\[]\s*(setItem|getItem)?\s*\(?\s*['\"]?[^'\"\]]*(token|refresh|secret|password|hos_access|hos_refresh)",
        re.IGNORECASE,
    )
    offenders = []
    for path in list(pathlib.Path("apps").rglob("*.ts")) + list(
        pathlib.Path("apps").rglob("*.tsx")
    ):
        if "node_modules" in path.parts or ".next" in path.parts:
            continue
        src = path.read_text()
        if tokenish.search(src):
            offenders.append(str(path))
    assert offenders == [], f"token storage in browser code: {offenders}"
