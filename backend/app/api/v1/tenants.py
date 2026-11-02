"""Tenant-scoped administration: locations, roles, memberships, invites,
practitioners + verification. Every route is permission-gated AND
tenant-matched (id != ctx.tenant_id -> 404, never 403-oracle).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_current_user, get_db, require
from app.api.v1._shared import match_tenant
from app.modules.audit import service as audit_service
from app.modules.clinics import service as clinics_service
from app.modules.identity import schemas as IS
from app.modules.identity.models import Practitioner, User
from app.modules.notifications import service as notify_service
from app.modules.tenancy import schemas as S
from app.modules.tenancy import service as tenancy_service
from app.modules.tenancy.models import Membership, Role, Verification
from app.platform.authz.permissions import P
from app.platform.authz.scope import RequestContext
from app.platform.errors import NotFoundError
from app.platform.ports.ports import NotifyRequest
from app.platform.request_context import request_id_ctx

router = APIRouter(tags=["tenants"])


def _audit(db: DBSession, ctx: RequestContext, *, action: str, rtype: str, rid: str) -> None:
    audit_service.append(
        db,
        tenant_id=ctx.tenant_id,
        actor_type="user",
        actor_id=str(ctx.user_id),
        action=action,
        resource_type=rtype,
        resource_id=rid,
        request_id=request_id_ctx.get(),
    )


@router.get("/tenants/mine", response_model=list[IS.TenantOption])
def my_tenants(
    user_session: tuple[User, object] = Depends(get_current_user),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[IS.TenantOption]:
    from app.api.v1._shared import tenant_options

    user, _ = user_session  # type: ignore[misc]
    return tenant_options(db, user)


@router.get("/tenants/{tenant_id}", response_model=S.TenantResponse)
def get_tenant(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.TENANT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.TenantResponse:
    match_tenant(ctx, tenant_id)
    t = tenancy_service.get_tenant(db, tenant_id)
    return S.TenantResponse(id=t.id, name=t.name, slug=t.slug, status=t.status)


@router.post("/tenants/{tenant_id}/locations", response_model=S.LocationResponse)
def create_location(
    tenant_id: uuid.UUID,
    body: S.LocationCreateRequest,
    ctx: RequestContext = Depends(require(P.LOCATIONS_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.LocationResponse:
    match_tenant(ctx, tenant_id)
    t = tenancy_service.get_tenant(db, tenant_id)
    loc = clinics_service.create_location(db, tenant=t, name=body.name, timezone=body.timezone)
    _audit(db, ctx, action="location.create", rtype="location", rid=str(loc.id))
    return S.LocationResponse(
        id=loc.id,
        tenant_id=loc.tenant_id,
        name=loc.name,
        timezone=loc.timezone,
        is_active=loc.is_active,
    )


@router.get("/tenants/{tenant_id}/locations", response_model=list[S.LocationResponse])
def list_locations(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.TENANT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.LocationResponse]:
    match_tenant(ctx, tenant_id)
    locs = clinics_service.list_locations(db, tenant_id=tenant_id)
    if ctx.location_ids:
        locs = [loc for loc in locs if loc.id in ctx.location_ids]
    return [
        S.LocationResponse(
            id=loc.id,
            tenant_id=loc.tenant_id,
            name=loc.name,
            timezone=loc.timezone,
            is_active=loc.is_active,
        )
        for loc in locs
    ]


@router.post("/tenants/{tenant_id}/roles", response_model=S.RoleResponse)
def create_role(
    tenant_id: uuid.UUID,
    body: S.RoleCreateRequest,
    ctx: RequestContext = Depends(require(P.ROLES_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.RoleResponse:
    match_tenant(ctx, tenant_id)
    t = tenancy_service.get_tenant(db, tenant_id)
    role = tenancy_service.create_custom_role(
        db, tenant=t, name=body.name, permissions=body.permissions
    )
    _audit(db, ctx, action="role.create", rtype="role", rid=str(role.id))
    return S.RoleResponse(
        id=role.id,
        tenant_id=role.tenant_id,
        name=role.name,
        permissions=list(role.permissions),
        is_seed=role.is_seed,
    )


@router.get("/tenants/{tenant_id}/roles", response_model=list[S.RoleResponse])
def list_roles(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.TENANT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.RoleResponse]:
    match_tenant(ctx, tenant_id)
    roles = (
        db.execute(select(Role).where((Role.tenant_id.is_(None)) | (Role.tenant_id == tenant_id)))
        .scalars()
        .all()
    )
    return [
        S.RoleResponse(
            id=r.id,
            tenant_id=r.tenant_id,
            name=r.name,
            permissions=list(r.permissions or []),
            is_seed=r.is_seed,
        )
        for r in roles
    ]


def _role_by_name(db: DBSession, tenant_id: uuid.UUID, name: str) -> Role:
    role = db.execute(
        select(Role).where(
            ((Role.tenant_id.is_(None)) | (Role.tenant_id == tenant_id)) & (Role.name == name)
        )
    ).scalar_one_or_none()
    if role is None:
        raise NotFoundError("role not found")
    return role


@router.get("/tenants/{tenant_id}/memberships", response_model=list[S.MembershipResponse])
def list_memberships(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.STAFF_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.MembershipResponse]:
    match_tenant(ctx, tenant_id)
    rows = db.execute(
        select(Membership, Role)
        .join(Role, Membership.role_id == Role.id)
        .where(Membership.tenant_id == tenant_id)
    ).all()
    out = []
    for m, role in rows:
        locs = tenancy_service.membership_location_ids(db, m.id)
        out.append(
            S.MembershipResponse(
                id=m.id,
                user_id=m.user_id,
                tenant_id=m.tenant_id,
                role=role.name,
                is_active=m.is_active,
                is_primary=m.is_primary,
                location_ids=locs,
            )
        )
    return out


@router.patch(
    "/tenants/{tenant_id}/memberships/{membership_id}",
    response_model=S.MembershipResponse,
)
def update_membership(
    tenant_id: uuid.UUID,
    membership_id: uuid.UUID,
    body: S.MembershipUpdateRequest,
    ctx: RequestContext = Depends(require(P.STAFF_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.MembershipResponse:
    match_tenant(ctx, tenant_id)
    m = db.get(Membership, membership_id)
    if m is None or m.tenant_id != tenant_id:
        raise NotFoundError("not found")
    role = None
    if body.role is not None:
        role = _role_by_name(db, tenant_id, body.role)
    updated = tenancy_service.update_membership(
        db,
        membership=m,
        role=role,
        is_active=body.is_active,
        location_ids=body.location_ids,
    )
    role_row = db.get(Role, updated.role_id)
    assert role_row is not None
    _audit(db, ctx, action="membership.update", rtype="membership", rid=str(updated.id))
    locs = tenancy_service.membership_location_ids(db, updated.id)
    return S.MembershipResponse(
        id=updated.id,
        user_id=updated.user_id,
        tenant_id=updated.tenant_id,
        role=role_row.name,
        is_active=updated.is_active,
        is_primary=updated.is_primary,
        location_ids=locs,
    )


@router.post("/tenants/{tenant_id}/invites", response_model=IS.InviteCreateResponse)
def create_invite(
    tenant_id: uuid.UUID,
    body: IS.InviteCreateRequest,
    ctx: RequestContext = Depends(require(P.STAFF_INVITE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> IS.InviteCreateResponse:
    match_tenant(ctx, tenant_id)
    t = tenancy_service.get_tenant(db, tenant_id)
    role = _role_by_name(db, tenant_id, body.role)
    inviter = db.get(User, ctx.user_id)
    inv, raw = tenancy_service.create_invitation(
        db, tenant=t, email=str(body.email), role=role, invited_by=inviter
    )
    notify_service.request_notification(
        db,
        NotifyRequest(
            channel="email",
            to_ref=inv.email,
            template="staff_invite",
            locale="en",
            context_refs={"invitation_id": str(inv.id)},
            tenant_id=tenant_id,
        ),
    )
    _audit(db, ctx, action="invite.create", rtype="invitation", rid=str(inv.id))
    return IS.InviteCreateResponse(id=inv.id, email=inv.email, token=raw, expires_at=inv.expires_at)


@router.post("/tenants/{tenant_id}/practitioners", response_model=S.PractitionerResponse)
def create_practitioner(
    tenant_id: uuid.UUID,
    body: S.PractitionerCreateRequest,
    ctx: RequestContext = Depends(require(P.STAFF_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PractitionerResponse:
    match_tenant(ctx, tenant_id)
    tenancy_service.get_tenant(db, tenant_id)
    linked = db.get(User, body.user_id) if body.user_id else None
    if body.user_id is not None and linked is None:
        raise NotFoundError("user not found")
    p = tenancy_service.register_practitioner(db, display_name=body.display_name, user=linked)
    tenancy_service.set_verification(
        db,
        tenant=tenancy_service.get_tenant(db, tenant_id),
        practitioner=p,
        status="pending",
    )
    _audit(db, ctx, action="practitioner.register", rtype="practitioner", rid=str(p.id))
    return S.PractitionerResponse(
        id=p.id, user_id=p.user_id, display_name=p.display_name, is_active=p.is_active
    )


@router.post("/tenants/{tenant_id}/verification", status_code=200)
def set_verification(
    tenant_id: uuid.UUID,
    body: S.VerificationRequest,
    ctx: RequestContext = Depends(require(P.STAFF_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> dict[str, str]:
    match_tenant(ctx, tenant_id)
    t = tenancy_service.get_tenant(db, tenant_id)
    p = db.get(Practitioner, body.practitioner_id)
    if p is None:
        raise NotFoundError("practitioner not found")
    reviewer = db.get(User, ctx.user_id)
    tenancy_service.set_verification(
        db,
        tenant=t,
        practitioner=p,
        status=body.status,
        reviewer=reviewer,
        reason=body.reason,
    )
    _audit(
        db,
        ctx,
        action=f"verification.{body.status}",
        rtype="practitioner",
        rid=str(p.id),
    )
    return {"status": body.status}


@router.get("/tenants/{tenant_id}/verification", response_model=list[dict])
def list_verifications(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.STAFF_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[dict]:
    match_tenant(ctx, tenant_id)
    rows = db.execute(
        select(Verification, Practitioner)
        .join(Practitioner, Verification.practitioner_id == Practitioner.id)
        .where(Verification.tenant_id == tenant_id)
    ).all()
    return [
        {
            "practitioner_id": str(p.id),
            "display_name": p.display_name,
            "status": v.status,
            "reason": v.reason,
        }
        for v, p in rows
    ]
