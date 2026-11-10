"""Atomic workspace provisioning (O1.2a): `POST /api/v1/workspaces`.

Single-transaction vertical slice. All records commit together or roll
back together — there is no partially provisioned tenant:

  tenant -> location -> membership (seed tenant_admin, is_primary) ->
  tenant_owners -> practitioner stub + pending verification ->
  tenant_specialties -> subscriptions (14-day trial) ->
  audit events -> transactional outbox event -> idempotency completion

Hard rules (enforced here, not in the API layer):
- No email-verification precondition (verification stays optional).
- No X-Tenant: the tenant is created here, scope is set server-side.
- Owner = the authenticated `user` row only. The request carries no
  owner/user ids (pydantic ignores extras; nothing here reads them).
- Plan, status, trial bounds are server-resolved from the seeded plan.
- Specialty codes are validated against the compile-time registry.
- Timezones must resolve via the IANA database (no silent fallback).
- Timestamps are UTC (`timestamptz`); the location timezone is preserved
  for local scheduling/display only.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections.abc import Sequence

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession

from app.modules.audit import service as audit_service
from app.modules.clinics import service as clinics_service
from app.modules.identity.models import Practitioner, User
from app.modules.notifications.eligibility import is_valid_iana_timezone
from app.modules.subscriptions import service as subscriptions_service
from app.modules.subscriptions.models import TRIAL_PLAN_CODE, SubscriptionPlan
from app.modules.tenancy import service as tenancy_service
from app.modules.tenancy.models import Tenant
from app.modules.workspaces import registry as specialty_registry
from app.modules.workspaces.models import (
    PROVISION_COMPLETED,
    PROVISION_PENDING,
    TenantSpecialty,
    WorkspaceProvision,
)
from app.modules.workspaces.schemas import (
    LocationRef,
    MembershipRef,
    PractitionerRef,
    SubscriptionRef,
    TenantRef,
    WorkspaceCreateRequest,
    WorkspaceResponse,
)
from app.platform import ids
from app.platform.errors import ConflictError, ValidationError
from app.platform.events import service as outbox_service
from app.platform.request_context import request_id_ctx
from app.platform.time import now as utcnow

_SLUG_RE = re.compile(r"^[a-z0-9-]{3,63}$")

# Authenticated-only availability check: slugs are inherently observable,
# so no oracle concern — but impersonation/squatting is blocked.
RESERVED_SLUGS = frozenset(
    {"platform", "api", "admin", "portal", "login", "signup", "verify", "health", "metrics"}
)

DEFAULT_LOCATION_NAME = "Main Clinic"


def _normalize(*, body: WorkspaceCreateRequest, user: User) -> dict[str, object]:
    clinic_name = body.clinic_name.strip()
    if not clinic_name:
        raise ValidationError("clinic name is required")
    slug = body.slug.strip().lower()
    if not _SLUG_RE.match(slug):
        raise ValidationError("slug must be 3-63 chars: lowercase letters, digits, hyphens")
    if slug in RESERVED_SLUGS:
        raise ValidationError(f"slug {slug!r} is reserved")
    location_name = (body.location_name or DEFAULT_LOCATION_NAME).strip() or DEFAULT_LOCATION_NAME
    if len(location_name) > 200:
        raise ValidationError("location name is too long")
    timezone_name = (body.timezone or "Asia/Kolkata").strip()
    if not is_valid_iana_timezone(timezone_name):
        raise ValidationError(f"unknown timezone: {body.timezone!r}")
    practitioner_name = (body.practitioner_display_name or user.display_name).strip()
    if not practitioner_name or len(practitioner_name) > 200:
        raise ValidationError("practitioner display name is required (1-200 chars)")
    specialties = specialty_registry.validate_specialty_codes(list(body.specialty_codes))
    return {
        "clinic_name": clinic_name,
        "slug": slug,
        "location_name": location_name,
        "timezone": timezone_name,
        "practitioner_name": practitioner_name,
        "specialties": specialties,
    }


def request_hash_for(*, normalized: dict[str, object]) -> str:
    specialties = normalized["specialties"]
    assert isinstance(specialties, list)
    canonical = json.dumps(
        {
            "clinic_name": normalized["clinic_name"],
            "slug": normalized["slug"],
            "location_name": normalized["location_name"],
            "timezone": normalized["timezone"],
            "practitioner_name": normalized["practitioner_name"],
            "specialty_codes": sorted(str(c) for c in specialties),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _response_from_refs(refs: dict[str, object]) -> WorkspaceResponse:
    return WorkspaceResponse.model_validate(refs)


def _find_claim(db: DBSession, *, user_id: uuid.UUID, key: str) -> WorkspaceProvision | None:
    return db.execute(
        select(WorkspaceProvision).where(
            WorkspaceProvision.user_id == user_id,
            WorkspaceProvision.idempotency_key == key,
        )
    ).scalar_one_or_none()


def _replay_or_conflict(claim: WorkspaceProvision, *, request_hash: str) -> WorkspaceResponse:
    if claim.request_hash != request_hash:
        raise ConflictError("idempotency key was used for a different request")
    if claim.status != PROVISION_COMPLETED or not claim.result_refs:
        # Same-transaction design: only `completed` rows survive commit, so
        # a hash-matching row is always replayable. Anything else is a
        # conflict rather than a silent re-execution.
        raise ConflictError("workspace provision already in progress")
    return _response_from_refs(dict(claim.result_refs))


def _provision_rows(
    db: DBSession, *, user: User, normalized: dict[str, object]
) -> WorkspaceResponse:
    now = utcnow()
    tenant = tenancy_service.create_tenant(
        db, name=str(normalized["clinic_name"]), slug=str(normalized["slug"])
    )
    # Server-derived scope for every tenant-scoped write below (same pattern
    # as invite acceptance: the tenant id comes from the insert, never the client).
    db.execute(text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant.id)})

    location = clinics_service.create_location(
        db,
        tenant=tenant,
        name=str(normalized["location_name"]),
        timezone=str(normalized["timezone"]),
    )
    role = tenancy_service.get_seed_role(db, "tenant_admin")
    membership = tenancy_service.create_membership(
        db, user=user, tenant=tenant, role=role, is_primary=True
    )
    tenancy_service.create_owner(db, tenant=tenant, user=user, created_by=user)

    practitioner = db.execute(
        select(Practitioner).where(Practitioner.user_id == user.id)
    ).scalar_one_or_none()
    if practitioner is None:
        practitioner = tenancy_service.register_practitioner(
            db, display_name=str(normalized["practitioner_name"]), user=user
        )
    else:
        # One person, one practitioner row shared across their tenants
        # (verification stays per-tenant below). Keep it active + labeled.
        practitioner.display_name = str(normalized["practitioner_name"])
        practitioner.is_active = True
    tenancy_service.set_verification(db, tenant=tenant, practitioner=practitioner, status="pending")

    specialties = normalized["specialties"]
    assert isinstance(specialties, list)
    codes = [str(c) for c in specialties]
    for code in codes:
        pack = specialty_registry.SPECIALTIES[code]
        db.add(
            TenantSpecialty(
                tenant_id=tenant.id,
                specialty_code=code,
                pack_version=pack.version,
                enabled_by=user.id,
                enabled_at=now,
            )
        )

    subscription = subscriptions_service.create_trial_subscription(db, tenant=tenant)
    plan = db.get(SubscriptionPlan, subscription.plan_id)

    request_id = request_id_ctx.get()
    audit_service.append(
        db,
        tenant_id=tenant.id,
        actor_type="user",
        actor_id=str(user.id),
        action="workspace.provision",
        resource_type="tenant",
        resource_id=str(tenant.id),
        request_id=request_id,
    )
    audit_service.append(
        db,
        tenant_id=tenant.id,
        actor_type="user",
        actor_id=str(user.id),
        action="subscription.trial.start",
        resource_type="subscription",
        resource_id=str(subscription.id),
        request_id=request_id,
    )
    outbox_service.emit(
        db,
        type="workspace.provisioned",
        aggregate="workspace",
        aggregate_id=str(tenant.id),
        tenant_id=tenant.id,
        payload={
            "tenant_id": str(tenant.id),
            "user_id": str(user.id),
            "location_id": str(location.id),
            "membership_id": str(membership.id),
            "practitioner_id": str(practitioner.id),
            "subscription_id": str(subscription.id),
        },
    )
    return WorkspaceResponse(
        tenant=TenantRef(id=tenant.id, name=tenant.name, slug=tenant.slug, status=tenant.status),
        location=LocationRef(id=location.id, name=location.name, timezone=location.timezone),
        membership=MembershipRef(id=membership.id, role="tenant_admin"),
        practitioner=PractitionerRef(id=practitioner.id, display_name=practitioner.display_name),
        specialties_enabled=codes,
        subscription=SubscriptionRef(
            id=subscription.id,
            status=subscription.status,
            trial_ends_at=subscription.trial_ends_at,
            plan_code=plan.code if plan is not None else TRIAL_PLAN_CODE,
        ),
    )


def provision_workspace(
    db: DBSession, *, user: User, body: WorkspaceCreateRequest, idempotency_key: str
) -> WorkspaceResponse:
    """Provision one workspace atomically. Must run inside the caller's
    transaction — the idempotency claim and all provisioned rows commit or
    roll back together."""
    normalized = _normalize(body=body, user=user)
    digest = request_hash_for(normalized=normalized)

    existing = _find_claim(db, user_id=user.id, key=idempotency_key)
    if existing is not None:
        return _replay_or_conflict(existing, request_hash=digest)

    now = utcnow()
    try:
        # Savepoint: a lost unique-race rolls back only the claim insert,
        # leaving the outer transaction usable for the replay read.
        with db.begin_nested():
            claim = WorkspaceProvision(
                id=ids.uuid7(),
                user_id=user.id,
                idempotency_key=idempotency_key,
                request_hash=digest,
                status=PROVISION_PENDING,
                created_at=now,
                updated_at=now,
            )
            db.add(claim)
            db.flush()
    except IntegrityError:
        # Lost the claim race: the winner committed (its insert blocked us
        # on the unique index until commit) or rolled back (then our insert
        # would have succeeded). Re-read and replay or report a mismatch.
        winner = _find_claim(db, user_id=user.id, key=idempotency_key)
        if winner is None:  # pragma: no cover - winner rolled back; retry once as fresh
            return provision_workspace(db, user=user, body=body, idempotency_key=idempotency_key)
        return _replay_or_conflict(winner, request_hash=digest)

    response = _provision_rows(db, user=user, normalized=normalized)
    claim.status = PROVISION_COMPLETED
    claim.tenant_id = response.tenant.id
    claim.result_refs = response.model_dump(mode="json")
    claim.updated_at = utcnow()
    return response


def get_tenant_specialties(db: DBSession, *, tenant: Tenant) -> list[str]:
    rows = db.execute(
        select(TenantSpecialty.specialty_code)
        .where(TenantSpecialty.tenant_id == tenant.id)
        .order_by(TenantSpecialty.specialty_code)
    ).all()
    return [r[0] for r in rows]


def specialty_rows_for_tenants(
    db: DBSession, *, tenant_ids: Sequence[object]
) -> dict[object, list[TenantSpecialty]]:
    """Batch specialty rows for platform reads (single query, no N+1)."""
    if not tenant_ids:
        return {}
    rows = (
        db.execute(
            select(TenantSpecialty)
            .where(TenantSpecialty.tenant_id.in_(tenant_ids))
            .order_by(TenantSpecialty.tenant_id, TenantSpecialty.specialty_code)
        )
        .scalars()
        .all()
    )
    out: dict[object, list[TenantSpecialty]] = {}
    for row in rows:
        out.setdefault(row.tenant_id, []).append(row)
    return out


def specialty_details_for_rows(rows: list[TenantSpecialty]) -> list[dict[str, object]]:
    """Read-model descriptors, sorted by code for deterministic output.

    Unknown codes fail safe to maturity "unknown" (never operational).
    Display only — never authorization input.
    """
    described = [
        specialty_registry.describe_specialty(r.specialty_code, r.pack_version) for r in rows
    ]
    described.sort(key=lambda d: str(d["code"]))
    return described


def get_tenant_specialty_rows(
    db: DBSession, *, tenant: Tenant
) -> list[TenantSpecialty]:
    return list(
        db.execute(
            select(TenantSpecialty)
            .where(TenantSpecialty.tenant_id == tenant.id)
            .order_by(TenantSpecialty.specialty_code)
        )
        .scalars()
        .all()
    )
