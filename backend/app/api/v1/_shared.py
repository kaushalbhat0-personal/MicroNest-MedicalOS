"""Shared API helpers (kept minimal; domain logic lives in services)."""
from sqlalchemy.orm import Session as DBSession

from app.modules.identity import schemas as S
from app.modules.identity.models import User
from app.modules.tenancy import service as tenancy_service


def tenant_options(db: DBSession, user: User) -> list[S.TenantOption]:
    out = []
    for m in tenancy_service.user_memberships(db, user.id):
        try:
            t = tenancy_service.get_tenant(db, m.tenant_id)
        except Exception:  # noqa: BLE001 — skip dangling, never fail the request
            continue
        out.append(S.TenantOption(id=t.id, slug=t.slug, name=t.name))
    return out
