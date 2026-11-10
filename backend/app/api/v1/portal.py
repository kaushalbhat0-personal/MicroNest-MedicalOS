"""Patient portal API boundary (/api/v1/portal).

Security contract (enforced here, never in the frontend):
- Every route requires `portal.read` (or a narrower portal perm) via the
  staff membership machinery, PLUS an active `portal_links` row binding the
  caller to exactly one patient in this tenant.
- `patient_id` is resolved server-side from the link. It never comes from
  the browser. Forged IDs fail closed with 404 (no oracle).
- Draft/internal states are never projected: signed prescriptions only,
  closed-encounter clinical only, issued financial snapshots only, document
  metadata only (storage keys never leave the server).
- Money is display-only: server-derived strings via MoneyDisplay-compatible
  shapes. No portal endpoint computes balances.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_current_user, get_db, require
from app.modules.audit import service as audit_service
from app.modules.audit.models import AuditEvent
from app.modules.billing.credit_notes import credit_notes_for_invoice
from app.modules.billing.estimates import estimate_lines, get_estimate, list_estimates
from app.modules.billing.invoices import (
    effective_allocated,
    get_invoice,
    invoice_lines,
    list_invoices,
    outstanding_for_invoice,
)
from app.modules.billing.models import (
    Estimate,
    EstimateLine,
    Invoice,
    InvoiceLine,
    Payment,
)
from app.modules.billing.payments import (
    allocated_for_payment,
    list_payments,
    patient_credit,
    unallocated_for_payment,
)
from app.modules.billing.receipts import receipt_for_payment
from app.modules.billing.refunds import refunds_for_payment
from app.modules.clinical import records as clinical_records
from app.modules.clinical import service as clinical_service
from app.modules.clinical.models import (
    DiagnosisCode,
    Encounter,
    ObservationType,
)
from app.modules.dental.models import Consent, DentalProcedure, TreatmentPlan
from app.modules.dental.plans import (
    get_plan,
    list_document_refs,
    list_plans,
    list_procedure_records,
    list_recalls,
    plan_items,
)
from app.modules.identity.models import User
from app.modules.patients import service as patients_service
from app.modules.patients.models import Patient
from app.modules.portal import schemas as S
from app.modules.portal import service as portal_service
from app.modules.portal.models import PortalLink
from app.modules.prescriptions import service as rx_service
from app.modules.prescriptions.models import Medication, Prescription, PrescriptionItem
from app.modules.scheduling import service as scheduling_service
from app.modules.scheduling.models import Appointment
from app.modules.tenancy import service as tenancy_service
from app.platform.authz.permissions import P
from app.platform.authz.scope import RequestContext
from app.platform.errors import NotFoundError, ValidationError
from app.platform.request_context import request_id_ctx

router = APIRouter(prefix="/portal", tags=["portal"])

PORTAL_ACTOR = "portal_user"


@dataclass
class PortalContext:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_name: str
    patient_id: uuid.UUID
    patient: Patient
    link: PortalLink


def portal_ctx(
    ctx: RequestContext = Depends(require(P.PORTAL_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> PortalContext:
    """Resolve the caller's single authorized patient context.

    Membership + `portal.read` pass first (existing machinery), then the
    portal link pins ownership. Any failure is 404: a portal caller without
    a link learns nothing about tenant structure.
    """
    try:
        link = portal_service.active_link(db, user_id=ctx.user_id, tenant_id=ctx.tenant_id)
        patient = patients_service.get_patient(
            db, tenant_id=ctx.tenant_id, patient_id=link.patient_id
        )
    except NotFoundError:
        raise NotFoundError("not found") from None
    if not patient.is_active:
        raise NotFoundError("not found")
    tenant = tenancy_service.get_tenant(db, ctx.tenant_id)
    return PortalContext(
        user_id=ctx.user_id,
        tenant_id=ctx.tenant_id,
        tenant_name=tenant.name,
        patient_id=patient.id,
        patient=patient,
        link=link,
    )


def _audit(
    db: DBSession,
    pc: PortalContext,
    *,
    action: str,
    resource_type: str,
    resource_id: str,
    encounter_id: str | None = None,
) -> None:
    audit_service.append(
        db,
        tenant_id=pc.tenant_id,
        actor_type=PORTAL_ACTOR,
        actor_id=str(pc.user_id),
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        encounter_id=encounter_id,
        request_id=request_id_ctx.get(),
    )


def _stmt_str(value: object) -> str:
    return str(value)


# --- appointments ---


def _appt_resp(a: Appointment) -> S.PortalAppointment:
    return S.PortalAppointment(
        id=a.id,
        start_at=a.start_at,
        end_at=a.end_at,
        timezone=a.timezone,
        status=a.status,
        location_id=a.location_id,
        notes=a.notes,
    )


@router.get("/workspaces", response_model=S.PortalWorkspaces)
def portal_workspaces(
    user_session: tuple[User, object] = Depends(get_current_user),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PortalWorkspaces:
    """Which workspaces may the caller use? Authentication-only (no portal
    permission required) so provider users can also query it for routing.
    Returns flags about the caller's own rows only."""
    user, _ = user_session
    w = portal_service.workspaces_for_user(db, user_id=user.id)
    return S.PortalWorkspaces(provider=w["provider"], portal=w["portal"])


@router.get("/me", response_model=S.PortalMe)
def portal_me(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PortalMe:
    user = db.get(User, pc.user_id)
    return S.PortalMe(
        user_id=pc.user_id,
        email=user.email if user else "",
        display_name=user.display_name if user else pc.patient.display_name,
        tenant_id=pc.tenant_id,
        tenant_name=pc.tenant_name,
        patient=S.PortalPatient(
            id=pc.patient.id,
            display_name=pc.patient.display_name,
            phone=pc.patient.phone,
            is_active=pc.patient.is_active,
        ),
    )


@router.get("/profile", response_model=S.PortalPatient)
def portal_profile(pc: PortalContext = Depends(portal_ctx)) -> S.PortalPatient:  # noqa: B008
    return S.PortalPatient(
        id=pc.patient.id,
        display_name=pc.patient.display_name,
        phone=pc.patient.phone,
        is_active=pc.patient.is_active,
    )


@router.get("/appointments", response_model=list[S.PortalAppointment])
def portal_appointments(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    status: str | None = None,
    limit: int = 50,
) -> list[S.PortalAppointment]:
    if status is not None and status not in scheduling_service.M.STATUSES:
        raise ValidationError("unknown status")
    q = (
        select(Appointment)
        .where(Appointment.tenant_id == pc.tenant_id, Appointment.patient_id == pc.patient_id)
        .order_by(Appointment.start_at.desc(), Appointment.id.desc())
    )
    if status is not None:
        q = q.where(Appointment.status == status)
    rows = list(db.execute(q.limit(min(max(limit, 1), 200))).scalars().all())
    return [_appt_resp(a) for a in rows]


@router.get("/appointments/{appointment_id}", response_model=S.PortalAppointment)
def portal_appointment(
    appointment_id: uuid.UUID,
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PortalAppointment:
    try:
        a = scheduling_service.get_appointment(
            db, tenant_id=pc.tenant_id, appointment_id=appointment_id
        )
    except NotFoundError:
        raise NotFoundError("not found") from None
    if a.patient_id != pc.patient_id:
        raise NotFoundError("not found")
    return _appt_resp(a)


@router.post("/appointments/{appointment_id}/cancel", response_model=S.PortalAppointment)
def portal_appointment_cancel(
    appointment_id: uuid.UUID,
    body: S.PortalAppointmentCancel,
    ctx: RequestContext = Depends(require(P.PORTAL_APPOINTMENT_CANCEL)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PortalAppointment:
    # Narrow-perm route: require() yields a RequestContext, so ownership is
    # resolved here through the same link choke point — never from the body.
    try:
        link_patient = portal_service.resolve_patient_id(
            db, user_id=ctx.user_id, tenant_id=ctx.tenant_id
        )
        patient = patients_service.get_patient(db, tenant_id=ctx.tenant_id, patient_id=link_patient)
    except NotFoundError:
        raise NotFoundError("not found") from None
    if not patient.is_active:
        raise NotFoundError("not found")
    try:
        a = scheduling_service.get_appointment(
            db, tenant_id=ctx.tenant_id, appointment_id=appointment_id
        )
    except NotFoundError:
        raise NotFoundError("not found") from None
    if a.patient_id != link_patient:
        raise NotFoundError("not found")
    if a.status not in (
        scheduling_service.M.STATUS_SCHEDULED,
        scheduling_service.M.STATUS_CONFIRMED,
    ):
        raise ValidationError("only scheduled or confirmed appointments can be cancelled here")
    cancelled = scheduling_service.cancel_appointment(
        db,
        tenant_id=ctx.tenant_id,
        appointment_id=appointment_id,
        actor_id=ctx.user_id,
        reason=body.reason,
    )
    audit_service.append(
        db,
        tenant_id=ctx.tenant_id,
        actor_type=PORTAL_ACTOR,
        actor_id=str(ctx.user_id),
        action="portal.appointment.cancel",
        resource_type="appointment",
        resource_id=str(appointment_id),
        request_id=request_id_ctx.get(),
    )
    return _appt_resp(cancelled)


# --- encounters / clinical summary (closed only) ---


def _encounter_resp(e: Encounter) -> S.PortalEncounter:
    return S.PortalEncounter(
        id=e.id,
        status=e.status,
        opened_at=e.opened_at,
        closed_at=e.closed_at,
        location_id=e.location_id,
    )


def _own_encounter(db: DBSession, pc: PortalContext, encounter_id: uuid.UUID) -> Encounter:
    try:
        e = clinical_service.get_encounter(db, tenant_id=pc.tenant_id, encounter_id=encounter_id)
    except NotFoundError:
        raise NotFoundError("not found") from None
    if e.patient_id != pc.patient_id:
        raise NotFoundError("not found")
    return e


@router.get("/encounters", response_model=list[S.PortalEncounter])
def portal_encounters(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    limit: int = 50,
) -> list[S.PortalEncounter]:
    rows, _ = clinical_service.list_encounters(
        db, tenant_id=pc.tenant_id, patient_id=pc.patient_id, limit=limit
    )
    return [_encounter_resp(e) for e in rows]


@router.get("/encounters/{encounter_id}", response_model=S.PortalEncounterDetail)
def portal_encounter(
    encounter_id: uuid.UUID,
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PortalEncounterDetail:
    e = _own_encounter(db, pc, encounter_id)
    detail = S.PortalEncounterDetail(
        id=e.id,
        status=e.status,
        opened_at=e.opened_at,
        closed_at=e.closed_at,
        location_id=e.location_id,
    )
    # Release rule: clinical content only for closed encounters, finalized
    # content only. Open encounters expose the visit header alone.
    if e.status != "closed":
        return detail
    notes = [
        S.PortalNote(
            id=n.id,
            note_type=n.note_type,
            status=n.status,
            is_addendum=n.is_addendum,
            subjective=n.subjective,
            objective=n.objective,
            assessment=n.assessment,
            plan=n.plan,
            created_at=n.created_at,
        )
        for n in clinical_records.list_notes(db, tenant_id=pc.tenant_id, encounter_id=e.id)
        if n.status in ("finalized", "amended")
    ]
    observations = [
        S.PortalObservation(
            id=o.id,
            type_code=(
                (lambda t: t.code if t is not None else "?")(db.get(ObservationType, o.type_id))
                if o.type_id
                else "?"
            ),
            value=o.value_text if o.value_text is not None else _stmt_str(o.value_numeric),
            unit=o.unit,
            recorded_at=o.taken_at,
        )
        for o in clinical_records.list_observations(db, tenant_id=pc.tenant_id, encounter_id=e.id)
    ]
    diagnoses = []
    for d in clinical_records.list_diagnoses(db, tenant_id=pc.tenant_id, encounter_id=e.id):
        if d.status not in ("active", "resolved"):
            continue
        code = display = None
        if d.diagnosis_id is not None:
            dc = db.get(DiagnosisCode, d.diagnosis_id)
            if dc is not None:
                code, display = dc.code, dc.display
        diagnoses.append(
            S.PortalDiagnosis(
                id=d.id, status=d.status, code=code, display=display, free_text=d.free_text
            )
        )
    detail.notes = notes
    detail.observations = observations
    detail.diagnoses = diagnoses
    _audit(
        db,
        pc,
        action="portal.encounter.read",
        resource_type="encounter",
        resource_id=str(e.id),
        encounter_id=str(e.id),
    )
    return detail


# --- prescriptions (signed only) ---


def _rx_resp(db: DBSession, p: Prescription) -> S.PortalPrescription:
    items = (
        db.execute(
            select(PrescriptionItem)
            .where(PrescriptionItem.prescription_id == p.id)
            .order_by(PrescriptionItem.line_no)
        )
        .scalars()
        .all()
    )
    out_items = []
    for i in items:
        med = db.get(Medication, i.medication_id)
        out_items.append(
            S.PortalPrescriptionItem(
                medication_code=med.code if med else "?",
                dose=i.dose,
                route=i.route,
                frequency=i.frequency,
                duration_days=i.duration_days,
                quantity=_stmt_str(i.quantity) if i.quantity is not None else None,
                instructions=i.instructions,
            )
        )
    return S.PortalPrescription(
        id=p.id,
        status=p.status,
        version=p.version,
        items=out_items,
        signed_at=p.signed_at,
        created_at=p.created_at,
    )


@router.get("/prescriptions", response_model=list[S.PortalPrescription])
def portal_prescriptions(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.PortalPrescription]:
    encounters, _ = clinical_service.list_encounters(
        db, tenant_id=pc.tenant_id, patient_id=pc.patient_id, limit=200
    )
    out: list[S.PortalPrescription] = []
    for e in encounters:
        for p in rx_service.list_prescriptions(db, tenant_id=pc.tenant_id, encounter_id=e.id):
            # Drafts and superseded chains are internal; patients see the
            # signed record (and its cancellation outcome) only.
            if p.status not in ("signed", "cancelled"):
                continue
            out.append(_rx_resp(db, p))
    _audit(
        db,
        pc,
        action="portal.prescriptions.read",
        resource_type="patient",
        resource_id=str(pc.patient_id),
    )
    return out


# --- dental ---


def _plan_resp(db: DBSession, plan: TreatmentPlan) -> S.PortalTreatmentPlan:
    items = []
    for i in plan_items(db, plan_id=plan.id):
        proc = db.get(DentalProcedure, i.procedure_id)
        items.append(
            S.PortalPlanItem(
                id=i.id,
                procedure_code=proc.code if proc else "?",
                procedure_display=proc.display if proc else None,
                tooth=i.tooth,
                surface=i.surface,
                status=i.status,
                notes=i.notes,
            )
        )
    return S.PortalTreatmentPlan(
        id=plan.id, status=plan.status, version=plan.version, notes=plan.notes, items=items
    )


@router.get("/treatment-plans", response_model=list[S.PortalTreatmentPlan])
def portal_plans(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.PortalTreatmentPlan]:
    return [
        _plan_resp(db, p) for p in list_plans(db, tenant_id=pc.tenant_id, patient_id=pc.patient_id)
    ]


@router.get("/treatment-plans/{plan_id}", response_model=S.PortalTreatmentPlan)
def portal_plan(
    plan_id: uuid.UUID,
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PortalTreatmentPlan:
    try:
        plan = get_plan(db, tenant_id=pc.tenant_id, plan_id=plan_id)
    except NotFoundError:
        raise NotFoundError("not found") from None
    if plan.patient_id != pc.patient_id:
        raise NotFoundError("not found")
    return _plan_resp(db, plan)


@router.get("/recalls", response_model=list[S.PortalRecall])
def portal_recalls(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.PortalRecall]:
    return [
        S.PortalRecall(
            id=r.id,
            due_date=r.due_date.isoformat() if isinstance(r.due_date, date) else str(r.due_date),
            reason=r.reason,
            status=r.status,
            location_id=r.location_id,
        )
        for r in list_recalls(db, tenant_id=pc.tenant_id, patient_id=pc.patient_id)
    ]


@router.get("/consents", response_model=list[S.PortalConsent])
def portal_consents(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.PortalConsent]:
    # Consents attach to plans or procedure records; both resolve to the
    # patient through the plan or the record's encounter.
    plan_ids = {p.id for p in list_plans(db, tenant_id=pc.tenant_id, patient_id=pc.patient_id)}
    encounters, _ = clinical_service.list_encounters(
        db, tenant_id=pc.tenant_id, patient_id=pc.patient_id, limit=200
    )
    record_ids: set[uuid.UUID] = set()
    for e in encounters:
        for rec in list_procedure_records(db, tenant_id=pc.tenant_id, encounter_id=e.id):
            record_ids.add(rec.id)
    rows = list(
        db.execute(
            select(Consent).where(Consent.tenant_id == pc.tenant_id).order_by(Consent.created_at)
        )
        .scalars()
        .all()
    )
    out = []
    for c in rows:
        if c.plan_id is not None and c.plan_id not in plan_ids:
            continue
        if c.plan_id is None and c.procedure_record_id not in record_ids:
            continue
        out.append(
            S.PortalConsent(
                id=c.id,
                status=c.status,
                consenter_name=c.consenter_name,
                consenter_relation=c.consenter_relation,
                decided_at=c.decided_at,
            )
        )
    return out


@router.get("/documents", response_model=list[S.PortalDocument])
def portal_documents(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> list[S.PortalDocument]:
    # Metadata only, closed encounters only. Storage keys never leave the
    # server; downloads are honestly unavailable in this release.
    encounters, _ = clinical_service.list_encounters(
        db,
        tenant_id=pc.tenant_id,
        patient_id=pc.patient_id,
        limit=200,
        status="closed",
    )
    out: list[S.PortalDocument] = []
    for e in encounters:
        for d in list_document_refs(db, tenant_id=pc.tenant_id, encounter_id=e.id):
            out.append(
                S.PortalDocument(
                    id=d.id,
                    doc_type=d.doc_type,
                    content_type=d.content_type,
                    size_bytes=d.size_bytes,
                    created_at=d.created_at,
                    download_available=False,
                )
            )
    _audit(
        db,
        pc,
        action="portal.documents.read",
        resource_type="patient",
        resource_id=str(pc.patient_id),
    )
    return out


# --- billing (issued snapshots, server-derived money) ---


def _money_lines(lines: list[EstimateLine] | list[InvoiceLine]) -> list[S.PortalMoneyLine]:
    return [
        S.PortalMoneyLine(
            description=ln.description,
            quantity=_stmt_str(ln.quantity),
            unit_rate=_stmt_str(ln.unit_rate),
            line_total=_stmt_str(ln.line_total),
        )
        for ln in lines
    ]


@router.get("/estimates", response_model=list[S.PortalEstimate])
def portal_estimates(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    limit: int = 50,
) -> list[S.PortalEstimate]:
    rows, _ = list_estimates(db, tenant_id=pc.tenant_id, patient_id=pc.patient_id, limit=limit)
    # Drafts are internal working documents; patients see issued snapshots.
    return [_estimate_resp(db, e) for e in rows if e.status != "draft"]


def _estimate_resp(db: DBSession, e: Estimate) -> S.PortalEstimate:
    return S.PortalEstimate(
        id=e.id,
        status=e.status,
        currency=e.currency,
        subtotal=_stmt_str(e.subtotal),
        tax_total=_stmt_str(e.tax_total),
        grand_total=_stmt_str(e.grand_total),
        valid_until=e.valid_until.isoformat() if e.valid_until else None,
        lines=_money_lines(estimate_lines(db, estimate_id=e.id)),
    )


@router.get("/estimates/{estimate_id}", response_model=S.PortalEstimate)
def portal_estimate(
    estimate_id: uuid.UUID,
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PortalEstimate:
    try:
        e = get_estimate(db, tenant_id=pc.tenant_id, estimate_id=estimate_id)
    except NotFoundError:
        raise NotFoundError("not found") from None
    if e.patient_id != pc.patient_id or e.status == "draft":
        raise NotFoundError("not found")
    return _estimate_resp(db, e)


@router.get("/invoices", response_model=list[S.PortalInvoice])
def portal_invoices(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    limit: int = 50,
) -> list[S.PortalInvoice]:
    rows, _ = list_invoices(db, tenant_id=pc.tenant_id, patient_id=pc.patient_id, limit=limit)
    return [_invoice_resp(db, i) for i in rows if i.status != "draft"]


def _invoice_resp(db: DBSession, inv: Invoice) -> S.PortalInvoice:
    return S.PortalInvoice(
        id=inv.id,
        status=inv.status,
        currency=inv.currency,
        subtotal=_stmt_str(inv.subtotal),
        tax_total=_stmt_str(inv.tax_total),
        grand_total=_stmt_str(inv.grand_total),
        allocated_amount=_stmt_str(effective_allocated(db, invoice_id=inv.id)),
        outstanding_amount=_stmt_str(outstanding_for_invoice(db, invoice=inv)),
        due_date=inv.due_date.isoformat() if inv.due_date else None,
        lines=_money_lines(invoice_lines(db, invoice_id=inv.id)),
    )


@router.get("/invoices/{invoice_id}", response_model=S.PortalInvoice)
def portal_invoice(
    invoice_id: uuid.UUID,
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PortalInvoice:
    try:
        inv = get_invoice(db, tenant_id=pc.tenant_id, invoice_id=invoice_id)
    except NotFoundError:
        raise NotFoundError("not found") from None
    if inv.patient_id != pc.patient_id or inv.status == "draft":
        raise NotFoundError("not found")
    _audit(db, pc, action="portal.invoice.read", resource_type="invoice", resource_id=str(inv.id))
    return _invoice_resp(db, inv)


@router.get("/payments", response_model=list[S.PortalPayment])
def portal_payments(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    limit: int = 50,
) -> list[S.PortalPayment]:
    rows, _ = list_payments(db, tenant_id=pc.tenant_id, patient_id=pc.patient_id, limit=limit)
    return [_payment_resp(db, p) for p in rows]


def _payment_resp(db: DBSession, p: Payment) -> S.PortalPayment:
    return S.PortalPayment(
        id=p.id,
        status=p.status,
        method=p.method,
        amount=_stmt_str(p.amount),
        allocated_amount=_stmt_str(allocated_for_payment(db, payment=p)),
        unallocated_amount=_stmt_str(unallocated_for_payment(db, payment=p)),
        currency=p.currency,
        received_at=p.received_at,
    )


@router.get("/credit-balance", response_model=S.PortalCreditBalance)
def portal_credit_balance(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
) -> S.PortalCreditBalance:
    credit = patient_credit(db, tenant_id=pc.tenant_id, patient_id=pc.patient_id)
    return S.PortalCreditBalance(currency="INR", credit=_stmt_str(credit))


@router.get("/receipts", response_model=list[S.PortalReceipt])
def portal_receipts(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    limit: int = 50,
) -> list[S.PortalReceipt]:
    rows, _ = list_payments(db, tenant_id=pc.tenant_id, patient_id=pc.patient_id, limit=limit)
    out: list[S.PortalReceipt] = []
    for p in rows:
        r = receipt_for_payment(db, payment_id=p.id)
        if r is None:
            continue
        out.append(
            S.PortalReceipt(
                id=r.id,
                payment_id=p.id,
                amount=_stmt_str(r.amount),
                currency=r.currency,
                created_at=r.created_at,
            )
        )
    return out


@router.get("/refunds", response_model=list[S.PortalRefund])
def portal_refunds(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    limit: int = 50,
) -> list[S.PortalRefund]:
    rows, _ = list_payments(db, tenant_id=pc.tenant_id, patient_id=pc.patient_id, limit=limit)
    out: list[S.PortalRefund] = []
    for p in rows:
        for r in refunds_for_payment(db, payment_id=p.id):
            out.append(
                S.PortalRefund(
                    id=r.id,
                    payment_id=p.id,
                    amount=_stmt_str(r.amount),
                    currency=r.currency,
                    status=r.status,
                    reason=r.reason,
                )
            )
    return out


@router.get("/credit-notes", response_model=list[S.PortalCreditNote])
def portal_credit_notes(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    limit: int = 50,
) -> list[S.PortalCreditNote]:
    rows, _ = list_invoices(db, tenant_id=pc.tenant_id, patient_id=pc.patient_id, limit=limit)
    out: list[S.PortalCreditNote] = []
    for inv in rows:
        if inv.status == "draft":
            continue
        for cn in credit_notes_for_invoice(db, invoice_id=inv.id):
            out.append(
                S.PortalCreditNote(
                    id=cn.id,
                    invoice_id=inv.id,
                    amount=_stmt_str(cn.amount),
                    currency=cn.currency,
                    status=cn.status,
                )
            )
    return out


# --- access log (own portal events only) ---


@router.get("/access-log", response_model=list[S.PortalAccessEvent])
def portal_access_log(
    pc: PortalContext = Depends(portal_ctx),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    limit: int = 50,
) -> list[S.PortalAccessEvent]:
    rows = list(
        db.execute(
            select(AuditEvent)
            .where(
                AuditEvent.tenant_id == pc.tenant_id,
                AuditEvent.actor_type == PORTAL_ACTOR,
                AuditEvent.actor_id == str(pc.user_id),
            )
            .order_by(AuditEvent.seq.desc())
            .limit(min(max(limit, 1), 200))
        )
        .scalars()
        .all()
    )
    return [
        S.PortalAccessEvent(
            action=r.action,
            resource_type=r.resource_type,
            resource_id=r.resource_id,
            occurred_at=r.occurred_at,
            request_id=r.request_id,
        )
        for r in rows
    ]
