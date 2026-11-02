"""v1 router. Thin: mounts module routers only."""
from fastapi import APIRouter

from app.api.v1 import account, audit, auth, invites, platform, tenants

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(account.router)
router.include_router(invites.router)
router.include_router(platform.router)
router.include_router(tenants.router)
router.include_router(audit.router)
