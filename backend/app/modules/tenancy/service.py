"""Tenancy service: tenants, roles, memberships (the only tenant attachment),
location scope, invitations, practitioner verification. All writes validate
scope server-side; client-sent tenant IDs are selectors only.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.modules.identity import service as identity_service
from app.modules.identity.models import Practitioner, User
from app.modules.tenancy.models import (
    TENANT_ACTIVE,
    Invitation,
    Membership,
    MembershipLocation,
    Role,
    Tenant,
    Verification,
)
from app.platform import ids
from app.platform.authz.permissions import PLATFORM_ONLY, P, validate_custom_role
from app.platform.errors import ConflictError, ForbiddenError, GoneError, NotFoundError
from app.platform.time import UTC


def _now() -> datetime:
    return datetime.now(UTC)


# --- Tenants (platform) ---


def create_tenant(db: DBSession, *, name: str, slug: str, actor: User | None = None) -> Tenant:
    slug_n = slug.strip().lower()
    if db.execute(select(Tenant).where(Tenant.slug == slug_n)).scalar_one_or_none():
        raise ConflictError("tenant slug already exists")
    now = _now()
    tenant = Tenant(
        id=ids.uuid7(),
        name=name,
        slug=slug_n,
        status=TENANT_ACTIVE,
        created_at=now,
        updated_at=now,
    )
    db.add(tenant)
    db.flush()
    return tenant


def get_tenant(db: DBSession, tenant_id: uuid.UUID) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise NotFoundError("tenant not found")
    return tenant


def set_tenant_status(db: DBSession, tenant: Tenant, *, status: str) -> Tenant:
    tenant.status = status
    tenant.updated_at = _now()
    return tenant


def get_seed_role(db: DBSession, name: str) -> Role:
    role = db.execute(
        select(Role).where(Role.tenant_id.is_(None), Role.name == name)
    ).scalar_one_or_none()
    if role is None:
        raise NotFoundError(f"seed role {name!r} missing")
    return role


# --- Memberships ---


def user_memberships(db: DBSession, user_id: uuid.UUID) -> list[Membership]:
    return list(
        db.execute(
            select(Membership).where(Membership.user_id == user_id, Membership.is_active.is_(True))
        )
        .scalars()
        .all()
    )


def get_membership(db: DBSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID) -> Membership:
    m = db.execute(
        select(Membership).where(
            Membership.user_id == user_id,
            Membership.tenant_id == tenant_id,
            Membership.is_active.is_(True),
        )
    ).scalar_one_or_none()
    if m is None:
        raise ForbiddenError("no active membership in tenant")
    return m


def membership_location_ids(db: DBSession, membership_id: uuid.UUID) -> list[uuid.UUID]:
    rows = db.execute(
        select(MembershipLocation.location_id).where(
            MembershipLocation.membership_id == membership_id
        )
    ).all()
    return [r[0] for r in rows]


def create_membership(
    db: DBSession,
    *,
    user: User,
    tenant: Tenant,
    role: Role,
    location_ids: list[uuid.UUID] | None = None,
    is_primary: bool = False,
) -> Membership:
    if role.tenant_id is not None and role.tenant_id != tenant.id:
        raise ForbiddenError("role belongs to another tenant")
    existing = db.execute(
        select(Membership).where(Membership.user_id == user.id, Membership.tenant_id == tenant.id)
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("membership already exists")
    now = _now()
    m = Membership(
        id=ids.uuid7(),
        user_id=user.id,
        tenant_id=tenant.id,
        role_id=role.id,
        is_active=True,
        is_primary=is_primary,
        created_at=now,
        updated_at=now,
    )
    db.add(m)
    db.flush()
    for loc_id in location_ids or []:
        db.add(MembershipLocation(membership_id=m.id, location_id=loc_id))
    return m


def create_custom_role(db: DBSession, *, tenant: Tenant, name: str, permissions: list[str]) -> Role:
    validate_custom_role(permissions)
    if set(permissions) & PLATFORM_ONLY:
        raise ForbiddenError("platform permissions cannot be granted to tenants")
    if db.execute(
        select(Role).where(Role.tenant_id == tenant.id, Role.name == name)
    ).scalar_one_or_none():
        raise ConflictError("role name already exists in tenant")
    role = Role(
        id=ids.uuid7(),
        tenant_id=tenant.id,
        name=name,
        permissions=sorted(set(permissions)),
        is_seed=False,
        created_at=_now(),
    )
    db.add(role)
    return role


# --- Invitations (create here; accept creates the membership) ---


def create_invitation(
    db: DBSession,
    *,
    tenant: Tenant,
    email: str,
    role: Role,
    invited_by: User | None,
    ttl_days: int = 7,
) -> tuple[Invitation, str]:
    if role.tenant_id is not None and role.tenant_id != tenant.id:
        raise ForbiddenError("role belongs to another tenant")
    raw = secrets.token_urlsafe(48)
    now = _now()
    inv = Invitation(
        id=ids.uuid7(),
        tenant_id=tenant.id,
        email=identity_service.normalize_email(email),
        role_id=role.id,
        invited_by=invited_by.id if invited_by else None,
        token_hash=hashlib.sha256(raw.encode()).hexdigest(),
        status="pending",
        expires_at=now + timedelta(days=ttl_days),
        accepted_at=None,
        created_at=now,
    )
    db.add(inv)
    return inv, raw


def find_invitation_tenant_id(db: DBSession, *, token: str) -> uuid.UUID:
    """Resolve the tenant for a token WITHOUT trusting client input.

    The invitations table is RLS-exempt (capability-gated by 256-bit token
    hash); the returned tenant id is server-derived and used to scope the
    accept transaction. Raises GoneError for unknown/expired tokens (no oracle
    either way: validity and expiry are indistinguishable).
    """
    digest = hashlib.sha256(token.encode()).hexdigest()
    tenant_id = db.execute(
        select(Invitation.tenant_id).where(
            Invitation.token_hash == digest,
            Invitation.status == "pending",
            Invitation.expires_at > _now(),
        )
    ).scalar_one_or_none()
    if tenant_id is None:
        raise GoneError("invitation invalid or expired")
    return tenant_id


def accept_invitation(
    db: DBSession, *, token: str, display_name: str, password: str
) -> tuple[User, Membership]:
    digest = hashlib.sha256(token.encode()).hexdigest()
    inv = db.execute(select(Invitation).where(Invitation.token_hash == digest)).scalar_one_or_none()
    if inv is None or inv.status != "pending" or inv.expires_at <= _now():
        raise GoneError("invitation invalid or expired")
    tenant = get_tenant(db, inv.tenant_id)
    if tenant.status != TENANT_ACTIVE:
        raise ForbiddenError("tenant is not active")
    role = db.get(Role, inv.role_id)
    if role is None:
        raise GoneError("invitation role no longer exists")
    user = identity_service.get_user_by_email(db, inv.email)
    if user is None:
        user = identity_service.create_user(
            db, email=inv.email, display_name=display_name, password=password
        )
    elif not user.is_active:
        raise ForbiddenError("user is deactivated")
    else:
        identity_service.set_password(db, user, password)
    membership = create_membership(db, user=user, tenant=tenant, role=role)
    inv.status = "accepted"
    inv.accepted_at = _now()
    identity_service.record_auth_event(
        db, action="invite_accepted", user_id=user.id, tenant_id=tenant.id
    )
    return user, membership


# --- Practitioner verification (enforced, not theater) ---


def register_practitioner(
    db: DBSession, *, display_name: str, user: User | None = None
) -> Practitioner:
    now = _now()
    p = Practitioner(
        id=ids.uuid7(),
        user_id=user.id if user else None,
        display_name=display_name,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(p)
    db.flush()
    return p


def set_verification(
    db: DBSession,
    *,
    tenant: Tenant,
    practitioner: Practitioner,
    status: str,
    reviewer: User | None = None,
    reason: str | None = None,
) -> Verification:
    if status not in ("pending", "approved", "rejected"):
        raise ValueError("invalid verification status")
    v = db.execute(
        select(Verification).where(
            Verification.tenant_id == tenant.id,
            Verification.practitioner_id == practitioner.id,
        )
    ).scalar_one_or_none()
    now = _now()
    if v is None:
        v = Verification(
            id=ids.uuid7(),
            tenant_id=tenant.id,
            practitioner_id=practitioner.id,
            status=status,
            reviewer_id=reviewer.id if reviewer else None,
            reason=reason,
            created_at=now,
            updated_at=now,
        )
        db.add(v)
    else:
        v.status = status
        v.reviewer_id = reviewer.id if reviewer else v.reviewer_id
        v.reason = reason
        v.updated_at = now
    return v


def is_practitioner_verified(
    db: DBSession, *, tenant_id: uuid.UUID, practitioner_id: uuid.UUID
) -> bool:
    v = db.execute(
        select(Verification).where(
            Verification.tenant_id == tenant_id,
            Verification.practitioner_id == practitioner_id,
        )
    ).scalar_one_or_none()
    return v is not None and v.status == "approved"


def _role_has_staff_manage(role: Role) -> bool:
    return P.STAFF_MANAGE in set(role.permissions or [])


def update_membership(
    db: DBSession,
    *,
    membership: Membership,
    role: Role | None = None,
    is_active: bool | None = None,
    location_ids: list[uuid.UUID] | None = None,
) -> Membership:
    """Change role / active / location scope. Never strand a tenant without
    administration: the last membership holding staff.manage cannot be
    deactivated or moved to a role without it."""
    target_active = membership.is_active if is_active is None else is_active
    target_role = role or db.get(Role, membership.role_id)
    if target_role is None:
        raise GoneError("role no longer exists")
    if target_role.tenant_id is not None and target_role.tenant_id != membership.tenant_id:
        raise ForbiddenError("role belongs to another tenant")
    if not target_active or not _role_has_staff_manage(target_role):
        current_role = db.get(Role, membership.role_id)
        if current_role is not None and _role_has_staff_manage(current_role):
            # Transactional guard (P4.8): lock the tenant's other active
            # memberships in a deterministic order before counting admins.
            # Without the row locks, two concurrent demotions could both read
            # a surviving admin and commit, stranding the tenant with none
            # (write skew under READ COMMITTED). Ordered locking avoids
            # deadlocks between competing demotions.
            others = db.execute(
                select(Membership, Role)
                .join(Role, Membership.role_id == Role.id)
                .where(
                    Membership.tenant_id == membership.tenant_id,
                    Membership.id != membership.id,
                    Membership.is_active.is_(True),
                )
                .order_by(Membership.id)
                .with_for_update(of=Membership)
            ).all()
            if not any(_role_has_staff_manage(r) for _, r in others):
                raise ForbiddenError("cannot remove the last tenant administrator")
    membership.role_id = target_role.id
    membership.is_active = target_active
    membership.updated_at = _now()
    if location_ids is not None:
        from sqlalchemy import delete as sa_delete

        from app.modules.clinics.models import Location
        from app.modules.tenancy.models import MembershipLocation as ML

        for loc_id in location_ids:
            loc = db.get(Location, loc_id)
            if loc is None or loc.tenant_id != membership.tenant_id:
                raise ForbiddenError("location is outside this tenant")
        db.execute(sa_delete(ML).where(ML.membership_id == membership.id))
        for loc_id in location_ids:
            db.add(ML(membership_id=membership.id, location_id=loc_id))
    return membership
