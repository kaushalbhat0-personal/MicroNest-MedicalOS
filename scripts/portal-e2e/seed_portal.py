"""Scratch portal validation seed (dev-only database healthcare_os_portalcheck)."""

import os
import sys
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, r"D:\Projects\micronest-medical-os\backend")

os.environ["JWT_SECRET"] = "x" * 40

from app.modules.billing import credit_notes as credit_notes_svc
from app.modules.billing import estimates as est_svc
from app.modules.billing import invoices as inv_svc
from app.modules.billing import payments as pay_svc
from app.modules.billing import receipts as receipt_svc
from app.modules.billing import service_catalog as catalog
from app.modules.clinical import records as clinical_records
from app.modules.clinical import service as clinical_service
from app.modules.dental import plans as dental_plans
from app.modules.identity import service as identity_service
from app.modules.patients import service as patients_service
from app.modules.portal import service as portal_service
from app.modules.prescriptions import service as rx_service
from app.modules.scheduling import service as scheduling_service
from app.modules.tenancy import service as tenancy_service
from app.platform import db as dbmod

OWNER = "postgresql+psycopg2://hos_owner:owner-dev-pass@127.0.0.1:5432/healthcare_os_portalcheck"


def main() -> None:
    factory = dbmod.make_session_factory(OWNER)
    db = factory()
    try:
        admin = identity_service.create_user(
            db, email="portal-admin@example.com", display_name="Portal Admin",
            password="Admin-pass-12345",
        )
        tenant = tenancy_service.create_tenant(db, name="Demo Clinic", slug="demo-portal")
        role = tenancy_service.get_seed_role(db, "tenant_admin")
        tenancy_service.create_membership(db, user=admin, tenant=tenant, role=role, is_primary=True)
        from app.modules.clinics import service as clinics_service

        location = clinics_service.create_location(db, tenant=tenant, name="Main Clinic")
        practitioner = tenancy_service.register_practitioner(db, display_name="Dr Demo")
        tenancy_service.set_verification(db, tenant=tenant, practitioner=practitioner, status="approved")
        patient = patients_service.register_patient(
            db, tenant_id=tenant.id, display_name="Maya Rao", phone="+911234567890"
        )
        db.commit()

        # Portal user with known password.
        portal_user = identity_service.create_user(
            db, email="maya@example.com", display_name="Maya Rao", password="Portal-pass-12345"
        )
        db.commit()
        portal_service.enroll_patient_user(
            db, tenant_id=tenant.id, email="maya@example.com", patient_id=patient.id,
            actor_id=admin.id,
        )
        db.commit()

        # Scheduled appointment tomorrow.
        start = datetime.now(timezone.utc) + timedelta(days=1)
        appt = scheduling_service.create_appointment(
            db, tenant_id=tenant.id, patient_id=patient.id, practitioner_id=practitioner.id,
            location_id=location.id, start=start.replace(microsecond=0), duration_minutes=30,
            actor_id=admin.id,
        )
        db.commit()

        # Closed encounter with finalized note, vitals, diagnosis, signed Rx.
        enc = clinical_service.open_encounter(
            db, tenant_id=tenant.id, actor_id=admin.id, patient_id=patient.id,
            practitioner_id=practitioner.id, location_id=location.id,
        )
        db.commit()
        note = clinical_records.create_note(
            db, tenant_id=tenant.id, encounter_id=enc.id, author_id=practitioner.id,
            note_type="general", subjective="Patient recovering well.",
        )
        clinical_records.finalize_note(
            db, tenant_id=tenant.id, note_id=note.id, actor_id=practitioner.id
        )
        clinical_records.record_observation(
            db, tenant_id=tenant.id, encounter_id=enc.id, type_code="bp_systolic",
            value_numeric=120, recorded_by=practitioner.id,
        )
        clinical_records.add_diagnosis(
            db, tenant_id=tenant.id, encounter_id=enc.id, diagnosis_code="I10",
            recorded_by=practitioner.id,
        )
        rx = rx_service.create_prescription(
            db, tenant_id=tenant.id, encounter_id=enc.id, prescribed_by=practitioner.id,
            items=[{"medication_code": "paracetamol-650", "dose": "650mg", "route": "oral",
                    "frequency": "TID", "instructions": "after food"}],
        )
        rx_service.sign_prescription(
            db, tenant_id=tenant.id, prescription_id=rx.id, actor_id=practitioner.id
        )
        db.commit()
        clinical_service.close_encounter(
            db, tenant_id=tenant.id, encounter_id=enc.id, actor_id=admin.id,
            reason="visit complete",
        )
        db.commit()

        # Dental plan + consent + recall + document.
        plan = dental_plans.create_plan(
            db, tenant_id=tenant.id, actor_id=admin.id, patient_id=patient.id,
            practitioner_id=practitioner.id,
        )
        dental_plans.create_consent(
            db, tenant_id=tenant.id, plan_id=plan.id, consenter_name="Maya Rao"
        )
        dental_plans.create_recall(
            db, tenant_id=tenant.id, actor_id=admin.id, patient_id=patient.id,
            practitioner_id=practitioner.id, location_id=location.id,
            due_date=date.today() + timedelta(days=30), reason="six month review",
        )
        dental_plans.create_document_ref(
            db, tenant_id=tenant.id, encounter_id=enc.id, doc_type="report",
            storage_key="demo/report-1.pdf", actor_id=admin.id,
        )
        db.commit()

        # Billing: issued estimate + issued invoice + payment + receipt.
        item = catalog.create_service(db, code="demo-fill", display="Filling", default_rate="200.00")
        est = est_svc.create_estimate(
            db, tenant_id=tenant.id, actor_id=admin.id, patient_id=patient.id,
            location_id=location.id,
            items=[{"service_catalog_id": item.id, "quantity": 1}],
        )
        est_svc.issue_estimate(db, tenant_id=tenant.id, estimate_id=est.id, actor_id=admin.id)
        inv = inv_svc.create_invoice(
            db, tenant_id=tenant.id, actor_id=admin.id, patient_id=patient.id,
            location_id=location.id,
            items=[{"service_catalog_id": item.id, "quantity": 1}],
        )
        inv_svc.issue_invoice(db, tenant_id=tenant.id, invoice_id=inv.id, actor_id=admin.id)
        pay = pay_svc.create_payment(
            db, tenant_id=tenant.id, actor_id=admin.id, patient_id=patient.id,
            location_id=location.id, method="upi", amount="100.00",
        )
        receipt_svc.create_receipt(db, tenant_id=tenant.id, payment_id=pay.id, actor_id=admin.id)
        db.commit()
        print("seed ok")
        print("portal login: maya@example.com / Portal-pass-12345")
    finally:
        db.close()


if __name__ == "__main__":
    main()
