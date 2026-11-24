"""Patient 360° longitudinal timeline — derived read model.

Aggregates existing domain rows (appointments, encounters, diagnoses,
prescriptions, treatment plans, billing, documents). No second writable
event table. Staff see clinic-internal drafts; portal audience only sees
released rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session as DBSession

from app.modules.billing.invoices import outstanding_for_invoice
from app.modules.billing.models import Invoice, Payment, Receipt
from app.modules.clinical import records as clinical_records
from app.modules.clinical import service as clinical_service
from app.modules.dental import plans as dental_plans
from app.modules.dental.models import PLAN_ACTIVE, PLAN_COMPLETED, PLAN_DRAFT, Recall, TreatmentPlan
from app.modules.patients import service as patients_service
from app.modules.prescriptions import service as rx_service
from app.modules.prescriptions.models import RX_CANCELLED, RX_DRAFT, RX_SIGNED
from app.modules.scheduling import service as sched
from app.platform.errors import NotFoundError, ValidationError
from app.platform.time import UTC, as_utc, now

Audience = Literal["staff", "portal"]
Category = Literal["admin", "scheduling", "clinical", "billing", "documents", "care"]

PORTAL_PLAN_STATUSES = frozenset({PLAN_ACTIVE, PLAN_COMPLETED})
PORTAL_RX_STATUSES = frozenset({RX_SIGNED, RX_CANCELLED})


@dataclass(frozen=True)
class TimelineItem:
    event_id: str
    kind: str
    category: Category
    occurred_at: datetime
    title: str
    summary: str | None
    resource_type: str
    resource_id: uuid.UUID
    location_id: uuid.UUID | None
    status: str | None
    href: str | None


@dataclass(frozen=True)
class PatientOverview:
    patient_id: uuid.UUID
    display_name: str
    phone: str | None
    email: str | None
    date_of_birth: date | None
    is_active: bool
    last_visit_at: datetime | None
    next_appointment_at: datetime | None
    next_appointment_id: uuid.UUID | None
    outstanding_balance: str
    currency: str
    follow_up_due: date | None
    open_followups: int = 0
    overdue_followups: int = 0
    completed_followups: int = 0


def _item(
    *,
    kind: str,
    category: Category,
    occurred_at: datetime,
    title: str,
    resource_type: str,
    resource_id: uuid.UUID,
    location_id: uuid.UUID | None = None,
    status: str | None = None,
    summary: str | None = None,
    href: str | None = None,
) -> TimelineItem:
    # Include kind in event_id so booked + completed for same appointment coexist.
    return TimelineItem(
        event_id=f"{kind}:{resource_id}",
        kind=kind,
        category=category,
        occurred_at=as_utc(occurred_at),
        title=title,
        summary=summary,
        resource_type=resource_type,
        resource_id=resource_id,
        location_id=location_id,
        status=status,
        href=href,
    )


def _appointments(
    db: DBSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> list[TimelineItem]:
    rows, _ = sched.list_appointments(
        db, tenant_id=tenant_id, patient_id=patient_id, limit=200
    )
    out: list[TimelineItem] = []
    for a in rows:
        out.append(
            _item(
                kind="appointment.booked",
                category="scheduling",
                occurred_at=a.created_at,
                title="Appointment booked",
                resource_type="appointment",
                resource_id=a.id,
                location_id=a.location_id,
                status=a.status,
                summary=f"Starts {as_utc(a.start_at).isoformat().replace('+00:00', 'Z')}",
                href=f"/schedule?focus={a.id}",
            )
        )
        if a.status == "checked_in" or (
            a.queue_token is not None and a.status in ("checked_in", "completed")
        ):
            out.append(
                _item(
                    kind="appointment.checked_in",
                    category="scheduling",
                    occurred_at=a.updated_at,
                    title="Patient checked in",
                    resource_type="appointment",
                    resource_id=a.id,
                    location_id=a.location_id,
                    status=a.status,
                    summary=f"Token {a.queue_token}" if a.queue_token else None,
                    href="/reception",
                )
            )
        if a.status == "no_show":
            out.append(
                _item(
                    kind="appointment.no_show",
                    category="scheduling",
                    occurred_at=a.updated_at,
                    title="Marked no-show",
                    resource_type="appointment",
                    resource_id=a.id,
                    location_id=a.location_id,
                    status=a.status,
                    href=f"/schedule?focus={a.id}",
                )
            )
        if a.status == "cancelled":
            out.append(
                _item(
                    kind="appointment.cancelled",
                    category="scheduling",
                    occurred_at=a.cancelled_at or a.updated_at,
                    title="Appointment cancelled",
                    resource_type="appointment",
                    resource_id=a.id,
                    location_id=a.location_id,
                    status=a.status,
                    href=f"/schedule?focus={a.id}",
                )
            )
        if a.status == "completed":
            out.append(
                _item(
                    kind="appointment.completed",
                    category="scheduling",
                    occurred_at=a.updated_at,
                    title="Visit completed",
                    resource_type="appointment",
                    resource_id=a.id,
                    location_id=a.location_id,
                    status=a.status,
                    href=f"/schedule?focus={a.id}",
                )
            )
    return out


def _encounters(
    db: DBSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, audience: Audience
) -> list[TimelineItem]:
    rows, _ = clinical_service.list_encounters(
        db, tenant_id=tenant_id, patient_id=patient_id, limit=200
    )
    out: list[TimelineItem] = []
    for e in rows:
        if audience == "portal" and e.status != "closed":
            continue
        out.append(
            _item(
                kind="encounter.opened",
                category="clinical",
                occurred_at=e.opened_at,
                title="Encounter opened",
                resource_type="encounter",
                resource_id=e.id,
                location_id=e.location_id,
                status=e.status,
                href=f"/encounters/{e.id}",
            )
        )
        if e.status == "closed" and e.closed_at is not None:
            out.append(
                _item(
                    kind="encounter.closed",
                    category="clinical",
                    occurred_at=e.closed_at,
                    title="Consultation completed",
                    resource_type="encounter",
                    resource_id=e.id,
                    location_id=e.location_id,
                    status=e.status,
                    href=f"/encounters/{e.id}",
                )
            )
            for d in clinical_records.list_diagnoses(
                db, tenant_id=tenant_id, encounter_id=e.id
            ):
                if audience == "portal" and d.status not in ("active", "resolved"):
                    continue
                if audience == "staff" and d.status == "superseded":
                    continue
                out.append(
                    _item(
                        kind="diagnosis.recorded",
                        category="clinical",
                        occurred_at=d.created_at,
                        title="Diagnosis recorded",
                        resource_type="diagnosis",
                        resource_id=d.id,
                        location_id=e.location_id,
                        status=d.status,
                        href=f"/encounters/{e.id}",
                    )
                )
    return out


def _prescriptions(
    db: DBSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, audience: Audience
) -> list[TimelineItem]:
    encounters, _ = clinical_service.list_encounters(
        db, tenant_id=tenant_id, patient_id=patient_id, limit=200
    )
    out: list[TimelineItem] = []
    for e in encounters:
        for p in rx_service.list_prescriptions(db, tenant_id=tenant_id, encounter_id=e.id):
            if audience == "portal" and p.status not in PORTAL_RX_STATUSES:
                continue
            if audience == "staff" and p.status == RX_DRAFT:
                out.append(
                    _item(
                        kind="prescription.draft",
                        category="clinical",
                        occurred_at=p.created_at,
                        title="Prescription draft",
                        resource_type="prescription",
                        resource_id=p.id,
                        location_id=e.location_id,
                        status=p.status,
                        href=f"/encounters/{e.id}",
                    )
                )
                continue
            if p.status in PORTAL_RX_STATUSES:
                out.append(
                    _item(
                        kind="prescription.signed",
                        category="clinical",
                        occurred_at=p.signed_at or p.created_at,
                        title="Prescription signed",
                        resource_type="prescription",
                        resource_id=p.id,
                        location_id=e.location_id,
                        status=p.status,
                        href=f"/encounters/{e.id}",
                    )
                )
    return out


def _plans(
    db: DBSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, audience: Audience
) -> list[TimelineItem]:
    rows = dental_plans.list_plans(db, tenant_id=tenant_id, patient_id=patient_id)
    out: list[TimelineItem] = []
    for p in rows:
        if audience == "portal" and p.status not in PORTAL_PLAN_STATUSES:
            continue
        if p.status == PLAN_DRAFT:
            out.append(
                _item(
                    kind="treatment_plan.draft",
                    category="clinical",
                    occurred_at=p.created_at,
                    title="Treatment plan draft",
                    resource_type="treatment_plan",
                    resource_id=p.id,
                    status=p.status,
                    href=f"/dental/plans/{p.id}",
                )
            )
        elif p.status in PORTAL_PLAN_STATUSES:
            out.append(
                _item(
                    kind="treatment_plan.published",
                    category="clinical",
                    occurred_at=p.updated_at,
                    title="Treatment plan published",
                    resource_type="treatment_plan",
                    resource_id=p.id,
                    status=p.status,
                    href=f"/dental/plans/{p.id}",
                )
            )
    return out


def _billing(
    db: DBSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, audience: Audience
) -> list[TimelineItem]:
    out: list[TimelineItem] = []
    invoices = list(
        db.execute(
            select(Invoice)
            .where(Invoice.tenant_id == tenant_id, Invoice.patient_id == patient_id)
            .order_by(Invoice.created_at)
        )
        .scalars()
        .all()
    )
    for inv in invoices:
        if audience == "portal" and inv.status == "draft":
            continue
        out.append(
            _item(
                kind="invoice.created",
                category="billing",
                occurred_at=inv.created_at,
                title="Invoice created",
                resource_type="invoice",
                resource_id=inv.id,
                location_id=inv.location_id,
                status=inv.status,
                href=f"/billing/invoices/{inv.id}",
            )
        )
    payments = list(
        db.execute(
            select(Payment)
            .where(Payment.tenant_id == tenant_id, Payment.patient_id == patient_id)
            .order_by(Payment.created_at)
        )
        .scalars()
        .all()
    )
    for pay in payments:
        out.append(
            _item(
                kind="payment.recorded",
                category="billing",
                occurred_at=pay.created_at,
                title="Payment recorded",
                resource_type="payment",
                resource_id=pay.id,
                location_id=pay.location_id,
                status=pay.status,
                href="/billing/payments",
            )
        )
        receipt = db.execute(
            select(Receipt).where(Receipt.payment_id == pay.id)
        ).scalar_one_or_none()
        if receipt is not None:
            out.append(
                _item(
                    kind="receipt.issued",
                    category="billing",
                    occurred_at=receipt.created_at,
                    title="Receipt issued",
                    resource_type="receipt",
                    resource_id=receipt.id,
                    location_id=receipt.location_id,
                    href=f"/billing/receipts/{receipt.id}",
                )
            )
    return out


def _documents(
    db: DBSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> list[TimelineItem]:
    encounters, _ = clinical_service.list_encounters(
        db, tenant_id=tenant_id, patient_id=patient_id, limit=200, status="closed"
    )
    out: list[TimelineItem] = []
    for e in encounters:
        for d in dental_plans.list_document_refs(
            db, tenant_id=tenant_id, encounter_id=e.id
        ):
            out.append(
                _item(
                    kind="document.uploaded",
                    category="documents",
                    occurred_at=d.created_at,
                    title="Document available",
                    resource_type="document",
                    resource_id=d.id,
                    location_id=e.location_id,
                    summary=d.doc_type,
                    href=f"/encounters/{e.id}",
                )
            )
    return out


def _registration(
    db: DBSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID
) -> list[TimelineItem]:
    patient = patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    return [
        _item(
            kind="patient.registered",
            category="admin",
            occurred_at=patient.created_at,
            title="Patient registered",
            resource_type="patient",
            resource_id=patient.id,
            href=f"/patients/{patient.id}",
        )
    ]


def _care_events(
    db: DBSession, *, tenant_id: uuid.UUID, patient_id: uuid.UUID, audience: Audience
) -> list[TimelineItem]:
    """Staff-only care ops events. Portal never sees internal follow-up notes."""
    if audience == "portal":
        return []
    from app.modules.communications import service as comms_service

    out: list[TimelineItem] = []
    for fu in comms_service.list_follow_ups(
        db, tenant_id=tenant_id, patient_id=patient_id, limit=200
    ):
        out.append(
            _item(
                kind="followup.created",
                category="care",
                occurred_at=fu.created_at,
                title="Follow-up created",
                resource_type="follow_up",
                resource_id=fu.id,
                location_id=fu.location_id,
                status=fu.status,
                summary=fu.reason,
                href="/follow-ups",
            )
        )
        if fu.status == "completed" and fu.completed_at is not None:
            out.append(
                _item(
                    kind="followup.completed",
                    category="care",
                    occurred_at=fu.completed_at,
                    title="Follow-up completed",
                    resource_type="follow_up",
                    resource_id=fu.id,
                    location_id=fu.location_id,
                    status=fu.status,
                    href="/follow-ups",
                )
            )
    for log in comms_service.list_communications(
        db, tenant_id=tenant_id, patient_id=patient_id, limit=100
    ):
        out.append(
            _item(
                kind="communication.logged",
                category="care",
                occurred_at=log.occurred_at,
                title="Communication logged",
                resource_type="communication_log",
                resource_id=log.id,
                location_id=log.location_id,
                status=log.outcome,
                summary=f"{log.channel} · {log.purpose}",
                href=f"/patients/{patient_id}",
            )
        )
    return out


def build_timeline(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    audience: Audience = "staff",
    category: Category | None = None,
    location_ids: frozenset[uuid.UUID] | None = None,
    limit: int = 50,
    cursor: str | None = None,
) -> tuple[list[TimelineItem], str | None]:
    """Return newest-first page. Cursor is ``{iso}|{event_id}`` opaque string."""
    patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)

    events: list[TimelineItem] = []
    events.extend(_registration(db, tenant_id=tenant_id, patient_id=patient_id))
    events.extend(_appointments(db, tenant_id=tenant_id, patient_id=patient_id))
    events.extend(
        _encounters(db, tenant_id=tenant_id, patient_id=patient_id, audience=audience)
    )
    events.extend(
        _prescriptions(db, tenant_id=tenant_id, patient_id=patient_id, audience=audience)
    )
    events.extend(_plans(db, tenant_id=tenant_id, patient_id=patient_id, audience=audience))
    events.extend(_billing(db, tenant_id=tenant_id, patient_id=patient_id, audience=audience))
    events.extend(_documents(db, tenant_id=tenant_id, patient_id=patient_id))
    events.extend(
        _care_events(db, tenant_id=tenant_id, patient_id=patient_id, audience=audience)
    )

    if category is not None:
        events = [e for e in events if e.category == category]
    if location_ids:
        events = [
            e for e in events if e.location_id is None or e.location_id in location_ids
        ]

    events.sort(key=lambda e: (e.occurred_at, e.event_id), reverse=True)

    seen: set[str] = set()
    deduped: list[TimelineItem] = []
    for e in events:
        if e.event_id in seen:
            continue
        seen.add(e.event_id)
        deduped.append(e)
    events = deduped

    if cursor:
        try:
            ts_raw, eid = cursor.split("|", 1)
            cursor_at = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
            if cursor_at.tzinfo is None:
                cursor_at = cursor_at.replace(tzinfo=UTC)
            events = [
                e
                for e in events
                if (e.occurred_at, e.event_id) < (as_utc(cursor_at), eid)
            ]
        except ValueError as exc:
            raise ValidationError("invalid cursor") from exc

    capped = min(max(limit, 1), 100)
    page = events[:capped]
    next_cursor = None
    if len(events) > capped:
        last = page[-1]
        next_cursor = (
            f"{last.occurred_at.isoformat().replace('+00:00', 'Z')}|{last.event_id}"
        )
    return page, next_cursor


def build_overview(
    db: DBSession,
    *,
    tenant_id: uuid.UUID,
    patient_id: uuid.UUID,
    location_ids: frozenset[uuid.UUID] | None = None,
) -> PatientOverview:
    patient = patients_service.get_patient(db, tenant_id=tenant_id, patient_id=patient_id)
    current = now()

    closed, _ = clinical_service.list_encounters(
        db, tenant_id=tenant_id, patient_id=patient_id, status="closed", limit=200
    )
    last_visit: datetime | None = None
    for e in closed:
        if e.closed_at is None:
            continue
        if last_visit is None or as_utc(e.closed_at) > as_utc(last_visit):
            last_visit = e.closed_at

    upcoming, _ = sched.list_appointments(
        db,
        tenant_id=tenant_id,
        patient_id=patient_id,
        start_from=current,
        limit=50,
    )
    next_appt = None
    for a in upcoming:
        if a.status not in ("scheduled", "confirmed"):
            continue
        if location_ids and a.location_id not in location_ids:
            continue
        next_appt = a
        break

    outstanding = Decimal("0")
    currency = "INR"
    invoices = list(
        db.execute(
            select(Invoice).where(
                Invoice.tenant_id == tenant_id, Invoice.patient_id == patient_id
            )
        )
        .scalars()
        .all()
    )
    for inv in invoices:
        if inv.status in ("draft", "voided"):
            continue
        outstanding += outstanding_for_invoice(db, invoice=inv)
        currency = inv.currency or currency

    recall = (
        db.execute(
            select(Recall)
            .where(Recall.tenant_id == tenant_id, Recall.patient_id == patient_id)
            .order_by(Recall.due_date)
            .limit(1)
        )
        .scalars()
        .first()
    )

    from app.modules.communications import service as comms_service

    fu_summary = comms_service.patient_followup_summary(
        db, tenant_id=tenant_id, patient_id=patient_id
    )

    return PatientOverview(
        patient_id=patient.id,
        display_name=patient.display_name,
        phone=patient.phone,
        email=patient.email,
        date_of_birth=patient.date_of_birth,
        is_active=patient.is_active,
        last_visit_at=last_visit,
        next_appointment_at=next_appt.start_at if next_appt else None,
        next_appointment_id=next_appt.id if next_appt else None,
        outstanding_balance=str(outstanding),
        currency=currency,
        follow_up_due=recall.due_date if recall else None,
        open_followups=fu_summary["open"],
        overdue_followups=fu_summary["overdue"],
        completed_followups=fu_summary["completed"],
    )


def assert_portal_plan_visible(plan: TreatmentPlan) -> None:
    """Portal release gate: active/completed are published; drafts stay clinic-only."""
    if plan.status not in PORTAL_PLAN_STATUSES:
        raise NotFoundError("not found")


def filter_portal_plans(plans: list[TreatmentPlan]) -> list[TreatmentPlan]:
    return [p for p in plans if p.status in PORTAL_PLAN_STATUSES]
