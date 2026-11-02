"""Dental plans, procedure records, consents, recalls, document references.

Plans are clinical (never estimates/invoices). Procedure records describe
what was planned/performed, referencing the catalog — never duplicating it.
Consents bind to exactly one subject. Recalls are review dates, not a
campaign engine. Document rows are metadata pointers to storage objects."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.modules.clinical.service import get_encounter
from app.modules.dental import models as M
from app.modules.dental.models import (
    Consent,
    DentalProcedureRecord,
    DocumentReference,
    Recall,
    TreatmentPlan,
    TreatmentPlanItem,
)
from app.modules.dental.service import (
    _encounter_in_scope,
    _verified_practitioner,
    get_procedure,
    validate_surface,
    validate_tooth,
)
from app.modules.patients import service as patients_service
from app.platform import ids
from app.platform.errors import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.platform.time import UTC


def _now() -> datetime:
    return datetime.now(UTC)


def _scope_check(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    practitioner_id: uuid.UUID,
    encounter_id: uuid.UUID | None,
    location_ids: frozenset[uuid.UUID] | None,
) -> None:
    patient = patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    if not patient.is_active:
        raise ValidationError("patient is not active")
    _verified_practitioner(db, tenant_id=tenant_id, practitioner_id=practitioner_id)
    if encounter_id is not None:
        _encounter_in_scope(
            db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=location_ids
        )
    elif location_ids:
        raise ForbiddenError("location is outside your scope")


# --- Treatment plans ---


def create_plan(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    patient_id: uuid.UUID,
    practitioner_id: uuid.UUID,
    encounter_id: uuid.UUID | None = None,
    notes: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> TreatmentPlan:
    _scope_check(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        practitioner_id=practitioner_id,
        encounter_id=encounter_id,
        location_ids=location_ids,
    )
    now = _now()
    plan = TreatmentPlan(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        encounter_id=encounter_id,
        practitioner_id=practitioner_id,
        status=M.PLAN_DRAFT,
        version=1,
        notes=(notes or "").strip() or None,
        created_by=actor_id,
        created_at=now,
        updated_at=now,
    )
    db.add(plan)
    db.flush()
    return plan


def get_plan(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> TreatmentPlan:
    plan = db.get(TreatmentPlan, plan_id)
    if plan is None or plan.tenant_id != tenant_id:
        raise NotFoundError("treatment plan not found")
    if location_ids is not None:
        _plan_location_scope(db, tenant_id=tenant_id, plan=plan, location_ids=location_ids)
    return plan


def plan_items(db: DBSession, *, plan_id: uuid.UUID) -> list[TreatmentPlanItem]:
    return list(
        db.execute(
            select(TreatmentPlanItem)
            .where(TreatmentPlanItem.plan_id == plan_id)
            .order_by(TreatmentPlanItem.sequence, TreatmentPlanItem.id)
        )
        .scalars()
        .all()
    )


def add_plan_item(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID,
    procedure_code: str,
    tooth: int | None = None,
    surface: str | None = None,
    sequence: int = 1,
    notes: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> TreatmentPlanItem:
    plan = get_plan(db, tenant_id=tenant_id, plan_id=plan_id, location_ids=location_ids)
    if location_ids and plan.encounter_id is not None:
        _encounter_in_scope(
            db, tenant_id=tenant_id, encounter_id=plan.encounter_id, location_ids=location_ids
        )
    if plan.status != M.PLAN_DRAFT:
        raise ConflictError("items can only change while the plan is a draft")
    validate_tooth(tooth)
    proc = get_procedure(db, code=procedure_code)
    now = _now()
    item = TreatmentPlanItem(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        plan_id=plan.id,
        procedure_id=proc.id,
        tooth=tooth,
        surface=validate_surface(surface),
        sequence=sequence,
        status=M.ITEM_PROPOSED,
        notes=(notes or "").strip() or None,
        created_at=now,
        updated_at=now,
    )
    db.add(item)
    db.flush()
    return item


def _plan_location_scope(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    plan: TreatmentPlan,
    location_ids: frozenset[uuid.UUID] | None,
) -> None:
    if location_ids and plan.encounter_id is None:
        raise ForbiddenError("location is outside your scope")
    if location_ids and plan.encounter_id is not None:
        _encounter_in_scope(
            db, tenant_id=tenant_id, encounter_id=plan.encounter_id, location_ids=location_ids
        )


def activate_plan(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> TreatmentPlan:
    plan = get_plan(db, tenant_id=tenant_id, plan_id=plan_id)
    _plan_location_scope(db, tenant_id=tenant_id, plan=plan, location_ids=location_ids)
    if plan.status != M.PLAN_DRAFT:
        raise ConflictError("only draft plans can be activated")
    if not plan_items(db, plan_id=plan.id):
        raise ValidationError("plan requires at least one item to activate")
    plan.status = M.PLAN_ACTIVE
    plan.version += 1
    plan.updated_at = _now()
    db.flush()
    return plan


def complete_plan(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> TreatmentPlan:
    plan = get_plan(db, tenant_id=tenant_id, plan_id=plan_id)
    _plan_location_scope(db, tenant_id=tenant_id, plan=plan, location_ids=location_ids)
    if plan.status != M.PLAN_ACTIVE:
        raise ConflictError("only active plans can be completed")
    open_items = [
        i
        for i in plan_items(db, plan_id=plan.id)
        if i.status not in (M.ITEM_COMPLETED, M.ITEM_CANCELLED)
    ]
    if open_items:
        raise ConflictError("plan has unfinished items")
    plan.status = M.PLAN_COMPLETED
    plan.version += 1
    plan.updated_at = _now()
    db.flush()
    return plan


def cancel_plan(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> TreatmentPlan:
    plan = get_plan(db, tenant_id=tenant_id, plan_id=plan_id)
    _plan_location_scope(db, tenant_id=tenant_id, plan=plan, location_ids=location_ids)
    if plan.status == M.PLAN_CANCELLED:
        return plan
    if plan.status not in (M.PLAN_DRAFT, M.PLAN_ACTIVE):
        raise ConflictError("plan cannot be cancelled")
    now = _now()
    for item in plan_items(db, plan_id=plan.id):
        if item.status not in (M.ITEM_COMPLETED, M.ITEM_CANCELLED):
            item.status = M.ITEM_CANCELLED
            item.updated_at = now
    plan.status = M.PLAN_CANCELLED
    plan.version += 1
    plan.updated_at = now
    db.flush()
    return plan


ITEM_TRANSITIONS: dict[str, frozenset[str]] = {
    M.ITEM_PROPOSED: frozenset({M.ITEM_PLANNED, M.ITEM_CANCELLED}),
    M.ITEM_PLANNED: frozenset({M.ITEM_IN_PROGRESS, M.ITEM_CANCELLED}),
    M.ITEM_IN_PROGRESS: frozenset({M.ITEM_COMPLETED, M.ITEM_CANCELLED}),
    M.ITEM_COMPLETED: frozenset(),
    M.ITEM_CANCELLED: frozenset(),
}


def transition_plan_item(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    to_status: str,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> TreatmentPlanItem:
    if to_status not in M.ITEM_STATUSES:
        raise ValidationError("unknown status")
    item = db.get(TreatmentPlanItem, item_id)
    if item is None or item.tenant_id != tenant_id:
        raise NotFoundError("plan item not found")
    plan = get_plan(db, tenant_id=tenant_id, plan_id=item.plan_id)
    _plan_location_scope(db, tenant_id=tenant_id, plan=plan, location_ids=location_ids)
    if item.status == to_status:
        return item
    if to_status not in ITEM_TRANSITIONS[item.status]:
        raise ValidationError(f"cannot move plan item from {item.status} to {to_status}")
    item.status = to_status
    item.updated_at = _now()
    db.flush()
    return item


def list_plans(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> list[TreatmentPlan]:
    patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    q = select(TreatmentPlan).where(
        TreatmentPlan.tenant_id == tenant_id, TreatmentPlan.patient_id == patient_id
    )
    plans = list(db.execute(q.order_by(TreatmentPlan.created_at)).scalars().all())
    if location_ids:
        out = []
        for plan in plans:
            if plan.encounter_id is None:
                continue
            enc = get_encounter(db, tenant_id=tenant_id, encounter_id=plan.encounter_id)
            if enc.location_id in location_ids:
                out.append(plan)
        return out
    return plans


# --- Procedure records ---


def record_procedure(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    practitioner_id: uuid.UUID,
    procedure_code: str,
    plan_item_id: uuid.UUID | None = None,
    tooth: int | None = None,
    surface: str | None = None,
    notes: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> DentalProcedureRecord:
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=location_ids
    )
    _verified_practitioner(db, tenant_id=tenant_id, practitioner_id=practitioner_id)
    validate_tooth(tooth)
    proc = get_procedure(db, code=procedure_code)
    if plan_item_id is not None:
        item = db.get(TreatmentPlanItem, plan_item_id)
        if item is None or item.tenant_id != tenant_id:
            raise NotFoundError("plan item not found")
    now = _now()
    record = DentalProcedureRecord(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        practitioner_id=practitioner_id,
        procedure_id=proc.id,
        plan_item_id=plan_item_id,
        tooth=tooth,
        surface=validate_surface(surface),
        status=M.RECORD_PLANNED,
        notes=(notes or "").strip() or None,
        created_at=now,
        updated_at=now,
    )
    db.add(record)
    db.flush()
    return record


def get_procedure_record(
    db: DBSession, *, tenant_id: uuid.UUID, record_id: uuid.UUID
) -> DentalProcedureRecord:
    record = db.get(DentalProcedureRecord, record_id)
    if record is None or record.tenant_id != tenant_id:
        raise NotFoundError("procedure record not found")
    return record


RECORD_TRANSITIONS: dict[str, frozenset[str]] = {
    M.RECORD_PLANNED: frozenset({M.RECORD_IN_PROGRESS, M.RECORD_CANCELLED}),
    M.RECORD_IN_PROGRESS: frozenset({M.RECORD_COMPLETED, M.RECORD_CANCELLED}),
    M.RECORD_COMPLETED: frozenset(),
    M.RECORD_CANCELLED: frozenset(),
}


def transition_procedure_record(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    record_id: uuid.UUID,
    to_status: str,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> DentalProcedureRecord:
    if to_status not in M.RECORD_STATUSES:
        raise ValidationError("unknown status")
    record = get_procedure_record(db, tenant_id=tenant_id, record_id=record_id)
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=record.encounter_id, location_ids=location_ids
    )
    if record.status == to_status:
        return record
    if to_status not in RECORD_TRANSITIONS[record.status]:
        raise ValidationError(f"cannot move procedure record from {record.status} to {to_status}")
    now = _now()
    record.status = to_status
    if to_status == M.RECORD_COMPLETED:
        record.performed_at = now
    record.updated_at = now
    db.flush()
    return record


def list_procedure_records(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> list[DentalProcedureRecord]:
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=location_ids
    )
    return list(
        db.execute(
            select(DentalProcedureRecord)
            .where(DentalProcedureRecord.encounter_id == encounter_id)
            .order_by(DentalProcedureRecord.created_at)
        )
        .scalars()
        .all()
    )


# --- Consents ---


def create_consent(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    plan_id: uuid.UUID | None = None,
    procedure_record_id: uuid.UUID | None = None,
    consenter_name: str,
    consenter_relation: str | None = None,
    document_ref: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Consent:
    if (plan_id is None) == (procedure_record_id is None):
        raise ValidationError("consent requires exactly one subject")
    name = (consenter_name or "").strip()
    if len(name) < 2 or len(name) > 200:
        raise ValidationError("consenter name must be 2-200 characters")
    if plan_id is not None:
        plan = get_plan(db, tenant_id=tenant_id, plan_id=plan_id)
        _plan_location_scope(db, tenant_id=tenant_id, plan=plan, location_ids=location_ids)
    else:
        assert procedure_record_id is not None
        record = get_procedure_record(db, tenant_id=tenant_id, record_id=procedure_record_id)
        _encounter_in_scope(
            db,
            tenant_id=tenant_id,
            encounter_id=record.encounter_id,
            location_ids=location_ids,
        )
    now = _now()
    consent = Consent(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        plan_id=plan_id,
        procedure_record_id=procedure_record_id,
        status=M.CONSENT_PENDING,
        consenter_name=name,
        consenter_relation=(consenter_relation or "").strip() or None,
        document_ref=(document_ref or "").strip() or None,
        created_at=now,
        updated_at=now,
    )
    db.add(consent)
    db.flush()
    return consent


def get_consent(db: DBSession, *, tenant_id: uuid.UUID, consent_id: uuid.UUID) -> Consent:
    consent = db.get(Consent, consent_id)
    if consent is None or consent.tenant_id != tenant_id:
        raise NotFoundError("consent not found")
    return consent


def _consent_scope(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    consent: Consent,
    location_ids: frozenset[uuid.UUID] | None,
) -> None:
    if consent.plan_id is not None:
        plan = get_plan(db, tenant_id=tenant_id, plan_id=consent.plan_id)
        _plan_location_scope(db, tenant_id=tenant_id, plan=plan, location_ids=location_ids)
    else:
        assert consent.procedure_record_id is not None
        record = get_procedure_record(
            db, tenant_id=tenant_id, record_id=consent.procedure_record_id
        )
        _encounter_in_scope(
            db,
            tenant_id=tenant_id,
            encounter_id=record.encounter_id,
            location_ids=location_ids,
        )


def decide_consent(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    consent_id: uuid.UUID,
    decision: str,
    actor_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Consent:
    if decision not in (M.CONSENT_GRANTED, M.CONSENT_DECLINED):
        raise ValidationError("unknown decision")
    consent = get_consent(db, tenant_id=tenant_id, consent_id=consent_id)
    _consent_scope(db, tenant_id=tenant_id, consent=consent, location_ids=location_ids)
    if consent.status != M.CONSENT_PENDING:
        raise ConflictError("consent was already decided")
    now = _now()
    consent.status = decision
    consent.decided_by = actor_id
    consent.decided_at = now
    consent.updated_at = now
    db.flush()
    return consent


def withdraw_consent(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    consent_id: uuid.UUID,
    actor_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Consent:
    consent = get_consent(db, tenant_id=tenant_id, consent_id=consent_id)
    _consent_scope(db, tenant_id=tenant_id, consent=consent, location_ids=location_ids)
    if consent.status != M.CONSENT_GRANTED:
        raise ConflictError("only granted consent can be withdrawn")
    consent.status = M.CONSENT_WITHDRAWN
    consent.decided_by = actor_id
    consent.decided_at = _now()
    consent.updated_at = consent.decided_at
    db.flush()
    return consent


# --- Recalls ---


def create_recall(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    patient_id: uuid.UUID,
    practitioner_id: uuid.UUID | None,
    location_id: uuid.UUID,
    due_date: date,
    reason: str,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Recall:
    from app.modules.clinics import service as clinics_service

    patient = patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    if not patient.is_active:
        raise ValidationError("patient is not active")
    if practitioner_id is not None:
        _verified_practitioner(db, tenant_id=tenant_id, practitioner_id=practitioner_id)
    location = clinics_service.get_location(db, tenant_id=tenant_id, location_id=location_id)
    if not location.is_active:
        raise ValidationError("location is not active")
    if location_ids and location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")
    cleaned = (reason or "").strip()
    if len(cleaned) < 2 or len(cleaned) > 200:
        raise ValidationError("reason must be 2-200 characters")
    now = _now()
    recall = Recall(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        patient_id=patient_id,
        practitioner_id=practitioner_id,
        location_id=location_id,
        due_date=due_date,
        reason=cleaned,
        status=M.RECALL_SCHEDULED,
        created_by=actor_id,
        created_at=now,
        updated_at=now,
    )
    db.add(recall)
    db.flush()
    return recall


def get_recall(db: DBSession, *, tenant_id: uuid.UUID, recall_id: uuid.UUID) -> Recall:
    recall = db.get(Recall, recall_id)
    if recall is None or recall.tenant_id != tenant_id:
        raise NotFoundError("recall not found")
    return recall


def transition_recall(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    recall_id: uuid.UUID,
    to_status: str,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> Recall:
    if to_status not in M.RECALL_STATUSES:
        raise ValidationError("unknown status")
    recall = get_recall(db, tenant_id=tenant_id, recall_id=recall_id)
    if location_ids and recall.location_id not in location_ids:
        raise ForbiddenError("location is outside your scope")
    if recall.status == to_status:
        return recall
    if recall.status != M.RECALL_SCHEDULED:
        raise ConflictError("only scheduled recalls can transition")
    recall.status = to_status
    recall.updated_at = _now()
    db.flush()
    return recall


def list_recalls(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> list[Recall]:
    patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    rows = list(
        db.execute(
            select(Recall)
            .where(Recall.tenant_id == tenant_id, Recall.patient_id == patient_id)
            .order_by(Recall.due_date)
        )
        .scalars()
        .all()
    )
    if location_ids:
        rows = [r for r in rows if r.location_id in location_ids]
    return rows


# --- Document references ---

DOC_TYPES = frozenset({"xray", "scan", "photo", "report", "other"})


def create_document_ref(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    actor_id: uuid.UUID,
    doc_type: str = "other",
    storage_key: str,
    content_type: str | None = None,
    size_bytes: int | None = None,
    sha256: str | None = None,
    notes: str | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> DocumentReference:
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=location_ids
    )
    dtype = (doc_type or "other").strip().lower()
    if dtype not in DOC_TYPES:
        raise ValidationError(f"unsupported document type: {doc_type}")
    key = (storage_key or "").strip()
    if not key:
        raise ValidationError("storage key is required")
    now = _now()
    ref = DocumentReference(
        id=ids.uuid7(),
        tenant_id=tenant_id,
        encounter_id=encounter_id,
        doc_type=dtype,
        storage_key=key,
        content_type=(content_type or "").strip() or None,
        size_bytes=size_bytes,
        sha256=(sha256 or "").strip() or None,
        notes=(notes or "").strip() or None,
        uploaded_by=actor_id,
        created_at=now,
    )
    db.add(ref)
    db.flush()
    return ref


def list_document_refs(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    encounter_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> list[DocumentReference]:
    _encounter_in_scope(
        db, tenant_id=tenant_id, encounter_id=encounter_id, location_ids=location_ids
    )
    return list(
        db.execute(
            select(DocumentReference)
            .where(DocumentReference.encounter_id == encounter_id)
            .order_by(DocumentReference.created_at)
        )
        .scalars()
        .all()
    )
