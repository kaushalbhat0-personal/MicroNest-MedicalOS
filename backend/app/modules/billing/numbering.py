"""Billing numbering + financial-year authority (pure helpers, no DB).

Series key: (tenant, location, financial_year, doc_type). Numbers are
allocated at issue/capture by the service layer under an advisory lock;
this module only builds and validates the deterministic inputs. Gaps are
accepted; duplicates are rejected by per-series UNIQUE constraints."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.platform.errors import ValidationError

DOC_INVOICE = "invoice"
DOC_RECEIPT = "receipt"
DOC_CREDIT_NOTE = "credit_note"
DOC_TYPES = (DOC_INVOICE, DOC_RECEIPT, DOC_CREDIT_NOTE)

KOLKATA_TZ = "Asia/Kolkata"


def validate_doc_type(doc_type: str) -> str:
    if doc_type not in DOC_TYPES:
        raise ValidationError(f"unknown document type: {doc_type}")
    return doc_type


def fy_for(value: date | datetime, *, tz: str = KOLKATA_TZ) -> str:
    """India FY Apr 1 → Mar 31 in Asia/Kolkata. April 2026 → FY2026-27."""
    zone = ZoneInfo(tz)
    if isinstance(value, datetime):
        local = value.astimezone(zone) if value.tzinfo else value.replace(tzinfo=zone)
        year, month = local.year, local.month
    else:
        year, month = value.year, value.month
    start = year if month >= 4 else year - 1
    return f"FY{start}-{str(start + 1)[-2:]}"


def validate_fy(value: str) -> str:
    import re

    if not re.fullmatch(r"FY\d{4}-\d{2}", value or ""):
        raise ValidationError(f"invalid financial year: {value}")
    start = int(value[2:6])
    if int(value[7:9]) != (start + 1) % 100:
        raise ValidationError(f"invalid financial year: {value}")
    return value


def series_key(
    *, tenant_id: object, location_id: object, financial_year: str, doc_type: str
) -> dict[str, object]:
    """Deterministic series identity validated in one place."""
    return {
        "tenant_id": tenant_id,
        "location_id": location_id,
        "financial_year": validate_fy(financial_year),
        "doc_type": validate_doc_type(doc_type),
    }
