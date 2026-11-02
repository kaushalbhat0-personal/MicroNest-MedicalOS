"""Tenancy service: tenants, memberships, last-admin guard, invites, verification."""

import pytest

from app.modules.tenancy import service
from app.platform.errors import (
    ConflictError,
    ForbiddenError,
    GoneError,
    ValidationError,
)


def _setup(owner_db, make_owner_user, make_tenant, role="tenant_admin"):  # type: ignore[no-untyped-def]
    user = make_owner_user()
    tenant = make_tenant()
    seed = service.get_seed_role(owner_db, role)
    membership = service.create_membership(
        owner_db, user=user, tenant=tenant, role=seed
    )
    owner_db.commit()
    return user, tenant, membership


def test_tenant_slug_unique(owner_db, make_tenant) -> None:  # type: ignore[no-untyped-def]
    make_tenant(slug="same-slug")
    with pytest.raises(ConflictError):
        service.create_tenant(owner_db, name="x", slug="same-slug")


def test_membership_unique_per_user_tenant(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    user, tenant, _ = _setup(owner_db, make_owner_user, make_tenant)
    with pytest.raises(ConflictError):
        service.create_membership(
            owner_db,
            user=user,
            tenant=tenant,
            role=service.get_seed_role(owner_db, "staff"),
        )


def test_last_admin_cannot_be_deactivated(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    _, _, membership = _setup(owner_db, make_owner_user, make_tenant)
    with pytest.raises(ForbiddenError):
        service.update_membership(owner_db, membership=membership, is_active=False)


def test_last_admin_cannot_be_demoted(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    _, tenant, membership = _setup(owner_db, make_owner_user, make_tenant)
    staff = service.get_seed_role(owner_db, "staff")
    with pytest.raises(ForbiddenError):
        service.update_membership(owner_db, membership=membership, role=staff)
    assert tenant.status == "active"


def test_second_admin_allows_first_to_leave(
    owner_db, make_owner_user, make_tenant
) -> None:  # type: ignore[no-untyped-def]
    user, tenant, membership = _setup(owner_db, make_owner_user, make_tenant)
    user2 = make_owner_user()
    service.create_membership(
        owner_db,
        user=user2,
        tenant=tenant,
        role=service.get_seed_role(owner_db, "tenant_admin"),
    )
    service.update_membership(owner_db, membership=membership, is_active=False)
    owner_db.commit()
    with pytest.raises(ForbiddenError):
        service.get_membership(owner_db, user_id=user.id, tenant_id=tenant.id)


def test_custom_role_subset_and_platform_rejected(owner_db, make_tenant) -> None:  # type: ignore[no-untyped-def]
    tenant = make_tenant()
    role = service.create_custom_role(
        owner_db,
        tenant=tenant,
        name="billing-clerk",
        permissions=["tenant.read", "billing.read"],
    )
    assert set(role.permissions) == {"tenant.read", "billing.read"}
    with pytest.raises((ValueError, ValidationError)):
        service.create_custom_role(
            owner_db, tenant=tenant, name="evil", permissions=["platform.tenant.create"]
        )


def test_invite_accept_flow(owner_db, make_owner_user, make_tenant) -> None:  # type: ignore[no-untyped-def]
    admin, tenant, _ = _setup(owner_db, make_owner_user, make_tenant)
    role = service.get_seed_role(owner_db, "receptionist")
    inv, raw = service.create_invitation(
        owner_db, tenant=tenant, email="newbie@example.com", role=role, invited_by=admin
    )
    owner_db.commit()
    user, membership = service.accept_invitation(
        owner_db, token=raw, display_name="Newbie", password="password-12345-abc"
    )
    owner_db.commit()
    assert membership.tenant_id == tenant.id
    # Single-use.
    with pytest.raises(GoneError):
        service.accept_invitation(
            owner_db, token=raw, display_name="x", password="password-12345-abc"
        )


def test_practitioner_verification(owner_db, make_tenant, make_owner_user) -> None:  # type: ignore[no-untyped-def]
    _, tenant, _ = _setup(owner_db, make_owner_user, make_tenant)
    p = service.register_practitioner(owner_db, display_name="Dr Rao")
    assert not service.is_practitioner_verified(
        owner_db, tenant_id=tenant.id, practitioner_id=p.id
    )
    service.set_verification(owner_db, tenant=tenant, practitioner=p, status="approved")
    assert service.is_practitioner_verified(
        owner_db, tenant_id=tenant.id, practitioner_id=p.id
    )
