"""Server-derived request context. Client-supplied tenant identifiers are
SELECTORS ONLY: every field here is resolved from server-side state
(session -> user -> memberships) and re-validated per request.
"""
import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class RequestContext:
    user_id: uuid.UUID
    session_id: uuid.UUID
    tenant_id: uuid.UUID
    membership_id: uuid.UUID
    role: str
    permissions: frozenset[str] = field(default_factory=frozenset)
    location_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    is_platform_admin: bool = False
    request_id: str = ""


def has_permission(ctx: RequestContext, permission: str) -> bool:
    return permission in ctx.permissions


def may_access_location(ctx: RequestContext, location_id: uuid.UUID | None) -> bool:
    """Empty location scope on membership means all tenant locations."""
    if not ctx.location_ids:
        return True
    if location_id is None:
        return False
    return location_id in ctx.location_ids
