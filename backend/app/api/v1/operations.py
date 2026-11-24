"""Clinic operations dashboard API. Read-only composition of existing modules."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DBSession

from app.api.deps import get_db, require
from app.api.v1._shared import match_tenant
from app.modules.operations import schemas as S
from app.modules.operations import service as ops
from app.platform.authz.permissions import P
from app.platform.authz.scope import RequestContext
from app.platform.errors import ForbiddenError

router = APIRouter(tags=["operations"])


@router.get(
    "/tenants/{tenant_id}/locations/{location_id}/operations-dashboard",
    response_model=S.OperationsDashboardResponse,
)
def operations_dashboard(
    tenant_id: uuid.UUID,
    location_id: uuid.UUID,
    ctx: RequestContext = Depends(require(P.TENANT_READ)),  # noqa: B008
    db: DBSession = Depends(get_db),  # noqa: B008
    day: str | None = None,
    practitioner_id: uuid.UUID | None = None,
    status: str | None = None,
) -> S.OperationsDashboardResponse:
    """Location-aware daily operations snapshot.

    GET is read-only: no mutations, no audit noise for routine polling.
    Requires ``tenant.read``. Domain sections appear only when the actor
    also holds the corresponding domain read permission.
    """
    match_tenant(ctx, tenant_id)
    from app.modules.subscriptions.commercial_policy import assert_feature

    assert_feature(
        db,
        tenant_id=tenant_id,
        feature_key="operations_dashboard",
        mutate=False,
        operation="operations.dashboard",
    )
    # At least one operational domain permission is required beyond bare
    # tenant.read so patient-only / empty roles cannot probe metrics.
    useful = {
        P.APPOINTMENT_READ,
        P.FOLLOWUP_READ,
        P.BILLING_READ,
        P.STAFF_MANAGE,
    }
    if not (ctx.permissions & useful):
        raise ForbiddenError("no operations permissions for this workspace")

    data = ops.build_operations_dashboard(
        db,
        tenant_id=tenant_id,
        location_id=location_id,
        permissions=ctx.permissions,
        location_ids=ctx.location_ids or None,
        day=day,
        practitioner_id=practitioner_id,
        status=status,
    )
    return S.OperationsDashboardResponse.model_validate(data)
