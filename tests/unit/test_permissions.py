"""Permission catalog: platform-defined, bundles valid, custom-role rules."""
import pytest

from app.platform.authz.permissions import P, PLATFORM_ONLY, SEED_ROLES, validate_custom_role


def test_catalog_has_p1_permissions() -> None:
    for perm in (
        P.TENANT_READ, P.STAFF_INVITE, P.STAFF_MANAGE, P.ROLES_MANAGE,
        P.LOCATIONS_MANAGE, P.AUDIT_READ, P.PLATFORM_TENANT_CREATE,
    ):
        assert isinstance(perm, str) and "." in perm


def test_seed_roles_reference_known_permissions() -> None:
    known = {v for v in vars(P).values() if isinstance(v, str)}
    for role, perms in SEED_ROLES.items():
        assert perms <= known, role
    assert "patient" in SEED_ROLES and len(SEED_ROLES["patient"]) == 0


def test_custom_role_rejects_unknown() -> None:
    with pytest.raises(ValueError):
        validate_custom_role(["clinic.fly"])


def test_custom_role_rejects_platform_only() -> None:
    with pytest.raises(ValueError):
        validate_custom_role([P.PLATFORM_TENANT_CREATE])


def test_custom_role_accepts_subset() -> None:
    validate_custom_role([P.TENANT_READ, P.LOCATIONS_MANAGE])


def test_platform_admin_bundle_is_minimal() -> None:
    assert SEED_ROLES["platform_admin"] <= PLATFORM_ONLY
