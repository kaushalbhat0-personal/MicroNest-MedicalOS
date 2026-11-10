"""Portal link service: enrollment, resolution, revocation.

Enrollment is staff-gated at the API layer (`staff.manage`). Passwords are
never set or overwritten here: new users activate through the existing
public password-reset flow.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.modules.identity import service as identity_service
from app.modules.patients import service as patients_service
from app.modules.portal.models import LINK_ACTIVE, LINK_REVOKED, PortalLink
from app.modules.tenancy import service as tenancy_service
from app.modules.tenancy.models import TENANT_ACTIVE, Role
from app.platform.authz.permissions import P
from app.platform.errors import ConflictError, ForbiddenError, NotFoundError


def _now() -> datetime:
    return datetime.now(timezone.utc)


def active_link(db: DBSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID) -> PortalLink:
    """Return the caller's active link. Any failure is a no-oracle 404."""
    link = db.execute(
        select(PortalLink).where(
            PortalLink.user_id == user_id,
            PortalLink.tenant_id == tenant_id,
            PortalLink.status == LINK_ACTIVE,
        )
    ).scalar_one_or_none()
    if link is None:
        raise NotFoundError("not found")
    return link


def resolve_patient_id(db: DBSession, *, user_id: uuid.UUID, tenant_id: uuid.UUID) -> uuid.UUID:
    """The single choke point for portal ownership: user+tenant -> patient."""
    return active_link(db, user_id=user_id, tenant_id=tenant_id).patient_id


def enroll_patient_user(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    email: str,
    patient_id: uuid.UUID,
    actor_id: uuid.UUID,
    display_name: str | None = None,
) -> PortalLink:
    """Bind (or re-bind) a portal login to a patient. Staff-gated by caller.

    - Patient must belong to the tenant (forged IDs fail closed, no oracle).
    - Existing users keep their credentials: never reset passwords here.
    - New users get an unusable random password; they activate via the
      public password-reset flow.
    - Re-enrollment reactivates a revoked link instead of duplicating.
    """
    patient = patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    if not patient.is_active:
        raise ConflictError("patient is not active")

    email = identity_service.normalize_email(email)
    user = identity_service.get_user_by_email(db, email)
    if user is None:
        user = identity_service.create_user(
            db,
            email=email,
            display_name=display_name or patient.display_name,
            password=secrets.token_urlsafe(32),
        )
        db.flush()
    if not user.is_active:
        raise ConflictError("user is not active")

    try:
        membership = tenancy_service.get_membership(db, user_id=user.id, tenant_id=tenant_id)
    except ForbiddenError:
        membership = None
    if membership is None:
        tenant = tenancy_service.get_tenant(db, tenant_id)
        if tenant.status != TENANT_ACTIVE:
            raise ForbiddenError("tenant is not active")
        role = tenancy_service.get_seed_role(db, "patient")
        tenancy_service.create_membership(db, user=user, tenant=tenant, role=role)

    link = db.execute(
        select(PortalLink).where(PortalLink.user_id == user.id, PortalLink.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if link is None:
        link = PortalLink(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user.id,
            patient_id=patient.id,
            status=LINK_ACTIVE,
            created_by=actor_id,
            created_at=_now(),
        )
        db.add(link)
    else:
        link.patient_id = patient.id
        link.status = LINK_ACTIVE
        link.revoked_at = None
    db.flush()
    return link


def revoke_link(db: DBSession, *, tenant_id: uuid.UUID, link_id: uuid.UUID) -> PortalLink:
    """Revoke portal access. Unknown IDs are 404 (no oracle)."""
    link = db.execute(
        select(PortalLink).where(PortalLink.id == link_id, PortalLink.tenant_id == tenant_id)
    ).scalar_one_or_none()
    if link is None:
        raise NotFoundError("not found")
    if link.status != LINK_REVOKED:
        link.status = LINK_REVOKED
        link.revoked_at = _now()
    db.flush()
    return link


# Permissions that belong to the patient portal allow-list. A membership
# counts as provider access when its role grants anything beyond these.
PORTAL_ONLY_PERMS = frozenset({P.PORTAL_READ, P.PORTAL_APPOINTMENT_CANCEL})


def workspaces_for_user(db: DBSession, *, user_id: uuid.UUID) -> dict[str, bool]:
    """Which workspaces may this identity use? Server-authoritative routing
    signal for post-login navigation. Both flags derive from the user's own
    rows only — no existence information about anything else leaks."""
    provider = False
    for m in tenancy_service.user_memberships(db, user_id):
        role = db.get(Role, m.role_id)
        if role is None:
            continue
        if set(role.permissions or []) - PORTAL_ONLY_PERMS:
            provider = True
            break
    portal = (
        db.execute(
            select(PortalLink.id).where(
                PortalLink.user_id == user_id, PortalLink.status == LINK_ACTIVE
            )
        ).scalar_one_or_none()
        is not None
    )
    return {"provider": provider, "portal": portal}
