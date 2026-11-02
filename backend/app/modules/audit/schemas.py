"""Audit schemas. Reads are scoped to the caller's tenant."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class AuditEventResponse(BaseModel):
    id: uuid.UUID
    occurred_at: datetime
    tenant_id: uuid.UUID
    actor_type: str
    actor_id: str
    action: str
    resource_type: str
    resource_id: str
    request_id: str | None
    result: str
