"""Design-system integrity: tokens exist, statuses map backend truth, drift script clean."""

from __future__ import annotations

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOKENS = ROOT / "packages" / "ui" / "tokens.css"
STATUS_TS = ROOT / "packages" / "ui" / "status.ts"

# Backend-authoritative statuses (models.py enums across billing, clinical,
# prescriptions, dental, scheduling). The Status component must map every one;
# unknown strings must fail safe to neutral (asserted in test_status_unknown).
REQUIRED_STATUSES = {
    # scheduling/service.py TRANSITIONS
    "scheduled",
    "confirmed",
    "checked_in",
    "completed",
    "cancelled",
    "no_show",
    # clinical/models.py
    "open",
    "closed",
    "draft",
    "finalized",
    "amended",
    # prescriptions/models.py
    "signed",
    # billing/models.py invoice/payment/credit/refund
    "issued",
    "partially_paid",
    "paid",
    "voided",
    "void",
    "recorded",
    "partially_allocated",
    "allocated",
    "partially_refunded",
    "refunded",
    # dental/models.py plans/items/records/consent/recall
    "active",
    "proposed",
    "planned",
    "in_progress",
    "pending",
    "granted",
    "declined",
    "withdrawn",
    # extras used by UI summaries
    "partial",
    "overdue",
    "expired",
    "converted",
    "approved",
    "rejected",
    "revoked",
    "resolved",
    "ruled_out",
    "superseded",
    "current",
}


def _luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(c * 2 for c in hex_color)
    rgb = [int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4)]

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


def _token_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for match in re.finditer(
        r"(--hos-[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{3,8})", TOKENS.read_text()
    ):
        values[match.group(1)] = match.group(2)
    return values


def test_required_semantic_tokens_exist() -> None:
    src = TOKENS.read_text()
    for token in (
        "--hos-bg",
        "--hos-fg",
        "--hos-surface",
        "--hos-border",
        "--hos-border-strong",
        "--hos-text-primary",
        "--hos-text-muted",
        "--hos-primary",
        "--hos-danger",
        "--hos-success",
        "--hos-warning",
        "--hos-info",
        "--hos-focus-ring",
        "--hos-disabled-bg",
        "--hos-brand-primary",
        "--hos-density-control-compact",
        "--hos-density-row-dense",
        "--hos-radius-sm",
        "--hos-radius-md",
        "--hos-radius-pill",
        "--hos-font-sans",
        "--hos-font-mono",
    ):
        assert token in src, f"missing token {token}"


def test_text_contrast_aa() -> None:
    values = _token_values()
    pairs = [
        ("--hos-text-primary", "--hos-bg", 4.5),
        ("--hos-primary-foreground", "--hos-primary", 4.5),
        ("--hos-text-on-primary", "--hos-primary", 4.5),
        ("--hos-success", "--hos-bg", 4.5),
        ("--hos-focus-ring", "--hos-bg", 3.0),
    ]
    for fg, bg, minimum in pairs:
        ratio = _contrast(values[fg], values[bg])
        assert ratio >= minimum, f"{fg} on {bg}: {ratio:.2f} < {minimum}"


def test_status_map_covers_backend_statuses() -> None:
    src = STATUS_TS.read_text()
    keys = set(re.findall(r"^\s*([a-z_]+):", src, re.MULTILINE))
    missing = REQUIRED_STATUSES - keys
    assert not missing, f"unmapped backend statuses: {sorted(missing)}"
    assert "?? { tone:" in src or "?? {" in src, "unknown statuses must fail safe"


def test_drift_script_clean() -> None:
    proc = subprocess.run(
        ["python", "scripts/check-design-tokens.py"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
