"""Follow-ups, communication consent, and communication logs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_db, require
from app.api.v1._shared import match_tenant
from app.modules.audit import service as audit_service
from app.modules.communications import schemas as S
from app.modules.communications import service as comms
from app.modules.communications import whatsapp as wa
from app.modules.communications.models import CommunicationConsent, CommunicationLog, FollowUp
from app.modules.patients import service as patients_service
from app.platform.authz.permissions import P
from app.platform.authz.scope import RequestContext
from app.platform.errors import ForbiddenError, ValidationError
from app.platform.request_context import request_id_ctx

router = APIRouter(tags=["communications"])


def _audit(
    db: DBSession,
    ctx: RequestContext,
    *,
    action: str,
    rtype: str,
    rid: str,
) -> None:
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


def _fu_resp(row: FollowUp) -> S.FollowUpResponse:
    return S.FollowUpResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        patient_id=row.patient_id,
        location_id=row.location_id,
        assigned_user_id=row.assigned_user_id,
        due_at=row.due_at,
        category=row.category,
        reason=row.reason,
        source_type=row.source_type,
        source_id=row.source_id,
        priority=row.priority,
        status=row.status,
        outcome=row.outcome,
        next_action=row.next_action,
        next_due_at=row.next_due_at,
        snooze_until=row.snooze_until,
        created_at=row.created_at,
        updated_at=row.updated_at,
        completed_at=row.completed_at,
    )


def _consent_resp(row: CommunicationConsent) -> S.ConsentResponse:
    return S.ConsentResponse(
        id=row.id,
        patient_id=row.patient_id,
        channel=row.channel,
        purpose=row.purpose,
        status=row.status,
        capture_source=row.capture_source,
        captured_at=row.captured_at,
        revoked_at=row.revoked_at,
        is_current=row.is_current,
    )


def _log_resp(row: CommunicationLog) -> S.CommunicationLogResponse:
    return S.CommunicationLogResponse(
        id=row.id,
        patient_id=row.patient_id,
        location_id=row.location_id,
        follow_up_id=row.follow_up_id,
        channel=row.channel,
        purpose=row.purpose,
        outcome=row.outcome,
        staff_user_id=row.staff_user_id,
        occurred_at=row.occurred_at,
        note=row.note,
    )


@router.post("/tenants/{tenant_id}/follow-ups", response_model=S.FollowUpResponse)
def create_follow_up(
    tenant_id: uuid.UUID,
    body: S.FollowUpCreateRequest,
    ctx: RequestContext = Depends(require(P.FOLLOWUP_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.FollowUpResponse:
    match_tenant(ctx, tenant_id)
    row = comms.create_follow_up(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        patient_id=body.patient_id,
        location_id=body.location_id,
        due_at=body.due_at,
        category=body.category,
        reason=body.reason,
        source_type=body.source_type,
        source_id=body.source_id,
        priority=body.priority,
        assigned_user_id=body.assigned_user_id,
        next_action=body.next_action,
        location_ids=ctx.location_ids or None,
    )
    _audit(db, ctx, action="followup.created", rtype="follow_up", rid=str(row.id))
    return _fu_resp(row)


@router.get("/tenants/{tenant_id}/follow-ups", response_model=list[S.FollowUpResponse])
def list_follow_ups(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.FOLLOWUP_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    patient_id: uuid.UUID | None = None,
    assigned_user_id: uuid.UUID | None = None,
    location_id: uuid.UUID | None = None,
    status: str | None = None,
    category: str | None = None,
    priority: str | None = None,
    bucket: str | None = None,
    limit: int = 50,
) -> list[S.FollowUpResponse]:
    match_tenant(ctx, tenant_id)
    assignee = assigned_user_id
    if bucket == "assigned_to_me":
        assignee = ctx.user_id
    rows = comms.list_follow_ups(
        db,
        tenant_id=tenant_id,
        location_ids=ctx.location_ids or None,
        patient_id=patient_id,
        assigned_user_id=assignee,
        location_id=location_id,
        status=status,
        category=category,
        priority=priority,
        bucket=bucket,
        limit=limit,
    )
    return [_fu_resp(r) for r in rows]


@router.get("/tenants/{tenant_id}/follow-ups/{follow_up_id}", response_model=S.FollowUpResponse)
def get_follow_up(
    tenant_id: uuid.UUID,
    follow_up_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.FOLLOWUP_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.FollowUpResponse:
    match_tenant(ctx, tenant_id)
    return _fu_resp(
        comms.get_follow_up(
            db,
            tenant_id=tenant_id,
            follow_up_id=follow_up_id,
            location_ids=ctx.location_ids or None,
        )
    )


@router.post(
    "/tenants/{tenant_id}/follow-ups/{follow_up_id}/transition",
    response_model=S.FollowUpResponse,
)
def transition_follow_up(
    tenant_id: uuid.UUID,
    follow_up_id: uuid.UUID,
    body: S.FollowUpTransitionRequest,
    ctx: RequestContext = Depends(require(P.FOLLOWUP_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.FollowUpResponse:
    match_tenant(ctx, tenant_id)
    row = comms.transition_follow_up(
        db,
        tenant_id=tenant_id,
        follow_up_id=follow_up_id,
        actor_id=ctx.user_id,
        new_status=body.status,
        outcome=body.outcome,
        next_action=body.next_action,
        next_due_at=body.next_due_at,
        snooze_until=body.snooze_until,
        assigned_user_id=body.assigned_user_id,
        location_ids=ctx.location_ids or None,
    )
    action = {
        "completed": "followup.completed",
        "cancelled": "followup.cancelled",
        "snoozed": "followup.snoozed",
    }.get(body.status, "followup.transitioned")
    _audit(db, ctx, action=action, rtype="follow_up", rid=str(row.id))
    return _fu_resp(row)


@router.post(
    "/tenants/{tenant_id}/follow-ups/{follow_up_id}/assign",
    response_model=S.FollowUpResponse,
)
def assign_follow_up(
    tenant_id: uuid.UUID,
    follow_up_id: uuid.UUID,
    body: S.FollowUpAssignRequest,
    ctx: RequestContext = Depends(require(P.FOLLOWUP_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.FollowUpResponse:
    match_tenant(ctx, tenant_id)
    row = comms.assign_follow_up(
        db,
        tenant_id=tenant_id,
        follow_up_id=follow_up_id,
        assigned_user_id=body.assigned_user_id,
        location_ids=ctx.location_ids or None,
    )
    _audit(db, ctx, action="followup.assigned", rtype="follow_up", rid=str(row.id))
    return _fu_resp(row)


@router.post(
    "/tenants/{tenant_id}/communication-consents",
    response_model=S.ConsentResponse,
)
def record_consent(
    tenant_id: uuid.UUID,
    body: S.ConsentRecordRequest,
    ctx: RequestContext = Depends(require(P.COMM_CONSENT_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ConsentResponse:
    match_tenant(ctx, tenant_id)
    row = comms.record_consent(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        patient_id=body.patient_id,
        channel=body.channel,
        purpose=body.purpose,
        status=body.status,
        capture_source=body.capture_source,
    )
    action = (
        "communication.consent.granted"
        if body.status == "granted"
        else "communication.consent.denied"
    )
    _audit(db, ctx, action=action, rtype="communication_consent", rid=str(row.id))
    return _consent_resp(row)


@router.post(
    "/tenants/{tenant_id}/communication-consents/revoke",
    response_model=S.ConsentResponse,
)
def revoke_consent(
    tenant_id: uuid.UUID,
    body: S.ConsentRevokeRequest,
    ctx: RequestContext = Depends(require(P.COMM_CONSENT_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ConsentResponse:
    match_tenant(ctx, tenant_id)
    row = comms.revoke_consent(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        patient_id=body.patient_id,
        channel=body.channel,
        purpose=body.purpose,
    )
    _audit(
        db,
        ctx,
        action="communication.consent.revoked",
        rtype="communication_consent",
        rid=str(row.id),
    )
    return _consent_resp(row)


@router.get(
    "/tenants/{tenant_id}/patients/{patient_id}/communication-consents",
    response_model=list[S.ConsentResponse],
)
def list_consents(
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.COMM_CONSENT_MANAGE)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.ConsentResponse]:
    match_tenant(ctx, tenant_id)
    return [
        _consent_resp(r)
        for r in comms.list_current_consents(
            db, tenant_id=tenant_id, patient_id=patient_id
        )
    ]


@router.get(
    "/tenants/{tenant_id}/patients/{patient_id}/communication-eligibility",
    response_model=S.ConsentEligibilityResponse,
)
def check_eligibility(
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    channel: str,
    purpose: str,
    ctx: RequestContext = Depends(require(P.COMMUNICATION_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.ConsentEligibilityResponse:
    match_tenant(ctx, tenant_id)
    patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    status = comms.consent_status(
        db, tenant_id=tenant_id, patient_id=patient_id, channel=channel, purpose=purpose
    )
    return S.ConsentEligibilityResponse(
        patient_id=patient_id,
        channel=channel,
        purpose=purpose,
        status=status,
        eligible=status == "granted",
    )


@router.post(
    "/tenants/{tenant_id}/communication-logs",
    response_model=S.CommunicationLogResponse,
)
def create_communication_log(
    tenant_id: uuid.UUID,
    body: S.CommunicationLogCreateRequest,
    ctx: RequestContext = Depends(require(P.COMMUNICATION_LOG)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.CommunicationLogResponse:
    match_tenant(ctx, tenant_id)
    row = comms.log_communication(
        db,
        tenant_id=tenant_id,
        actor_id=ctx.user_id,
        patient_id=body.patient_id,
        channel=body.channel,
        purpose=body.purpose,
        outcome=body.outcome,
        location_id=body.location_id,
        follow_up_id=body.follow_up_id,
        note=body.note,
        occurred_at=body.occurred_at,
        location_ids=ctx.location_ids or None,
    )
    _audit(db, ctx, action="communication.logged", rtype="communication_log", rid=str(row.id))
    return _log_resp(row)


@router.get(
    "/tenants/{tenant_id}/communication-logs",
    response_model=list[S.CommunicationLogResponse],
)
def list_communication_logs(
    tenant_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.COMMUNICATION_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    patient_id: uuid.UUID | None = None,
    follow_up_id: uuid.UUID | None = None,
    limit: int = 50,
) -> list[S.CommunicationLogResponse]:
    match_tenant(ctx, tenant_id)
    rows = comms.list_communications(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        follow_up_id=follow_up_id,
        location_ids=ctx.location_ids or None,
        limit=limit,
    )
    return [_log_resp(r) for r in rows]


@router.post(
    "/tenants/{tenant_id}/whatsapp-link",
    response_model=S.WhatsAppLinkResponse,
)
def whatsapp_link(
    tenant_id: uuid.UUID,
    body: S.WhatsAppLinkRequest,
    ctx: RequestContext = Depends(require(P.COMMUNICATION_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.WhatsAppLinkResponse:
    """Build a wa.me URL. Never sends. Click is not proof of contact."""
    match_tenant(ctx, tenant_id)
    if body.purpose not in (
        "appointment_reminder",
        "care_followup",
        "administrative",
        "marketing",
    ):
        raise ValidationError("unknown purpose")
    patient = patients_service.get_patient(
        db, tenant_id=tenant_id, patient_id=body.patient_id
    )
    status = comms.consent_status(
        db,
        tenant_id=tenant_id,
        patient_id=body.patient_id,
        channel="whatsapp",
        purpose=body.purpose,
    )
    eligible = status == "granted"
    if body.require_consent and not eligible:
        raise ForbiddenError("WhatsApp communication is not consented for this purpose")
    if not patient.phone:
        raise ValidationError("patient has no phone number")
    url = wa.build_whatsapp_url(phone=patient.phone, message=body.message)
    _audit(
        db,
        ctx,
        action="communication.whatsapp_link_prepared",
        rtype="patient",
        rid=str(patient.id),
    )
    return S.WhatsAppLinkResponse(
        url=url,
        patient_id=patient.id,
        patient_display_name=patient.display_name,
        purpose=body.purpose,
        consent_status=status,
        eligible=eligible,
        auto_send=False,
        delivery_tracked=False,
    )
