"""v1 router. Thin: mounts module routers only."""

from fastapi import APIRouter

from app.api import errors as error_handlers
from app.api.v1 import account, audit, auth, invites, platform, tenants

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router, responses=error_handlers.AUTHN_RESPONSES)
router.include_router(account.router, responses=error_handlers.AUTHN_RESPONSES)
router.include_router(invites.router, responses=error_handlers.AUTHN_RESPONSES)
router.include_router(platform.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(tenants.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(audit.router, responses=error_handlers.AUTHZ_RESPONSES)
