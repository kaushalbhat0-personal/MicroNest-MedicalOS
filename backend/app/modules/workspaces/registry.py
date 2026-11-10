"""Typed, compile-time specialty registry (O1.2a).

First-party packs only: adding a specialty is a code change + registry entry
+ migration for its tables + tests. No dynamic loading, no marketplace, no
runtime module download. Packs configure workflows (terminology, nav, forms)
and NEVER identity, authorization, RLS, billing, or tenant isolation.

Keep `SPECIALTIES` keys in sync with migration 0016
(`ck_tenant_specialty_code`).

Ophthalmology is discovery-only until doctor sign-off: the code is a valid
enablement label, but no eye workflows, thresholds, or device logic exist
anywhere in the codebase.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SpecialtyPack:
    code: str
    version: str  # semver of the pack contract, stored per tenant at enablement
    label: str  # display name (i18n key, not free text)
    maturity: str  # "ready" | "discovery" — discovery packs build no workflows


SPECIALTIES: dict[str, SpecialtyPack] = {
    "dental": SpecialtyPack(
        code="dental",
        version="1.0.0",
        label="specialty.dental",
        maturity="ready",
    ),
    "ophthalmology": SpecialtyPack(
        code="ophthalmology",
        version="0.1.0",
        label="specialty.ophthalmology",
        maturity="discovery",
    ),
}


def validate_specialty_codes(codes: list[str]) -> list[str]:
    """Normalize + validate submitted codes against the registry.

    Returns deduplicated codes in registry order. Raises ValidationError on
    empty input or any unknown code. Both registry packs are accepted as
    enablement labels (ophthalmology enables no workflows yet — recorded
    explicitly, never silently mapped to dental).
    """
    from app.platform.errors import ValidationError

    seen: list[str] = []
    for raw in codes:
        code = str(raw).strip().lower()
        if code not in SPECIALTIES:
            raise ValidationError(f"unsupported specialty: {raw!r}")
        if code not in seen:
            seen.append(code)
    if not seen:
        raise ValidationError("at least one specialty is required")
    return seen


# Readiness metadata for the O1.3R read model. `ready_for_use` is a display
# predicate only: it NEVER gates authorization, RLS, tenant identity, or
# subscription behavior. Unknown codes (no registry entry) fail safe to
# `maturity="unknown"`, never operational.
def describe_specialty(code: str, pack_version: str) -> dict[str, object]:
    """Safe read-model descriptor for one persisted enablement row."""
    normalized = str(code).strip().lower()
    pack = SPECIALTIES.get(normalized)
    if pack is None:
        return {
            "code": normalized,
            "pack_version": str(pack_version),
            "label": normalized,
            "maturity": "unknown",
            "ready_for_use": False,
        }
    return {
        "code": pack.code,
        "pack_version": str(pack_version),
        "label": pack.label,
        "maturity": pack.maturity,
        "ready_for_use": pack.maturity == "ready",
    }
