"""v1 router. Thin: mounts module routers only."""

from fastapi import APIRouter

from app.api import errors as error_handlers
from app.api.v1 import (
    account,
    audit,
    auth,
    billing,
    communications,
    dental,
    encounters,
    inventory,
    invites,
    operations,
    patients,
    platform,
    portal,
    prescriptions,
    saas_payments,
    scheduling,
    signup,
    staff,
    subscriptions,
    tenants,
    workspaces,
)

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router, responses=error_handlers.AUTHN_RESPONSES)
router.include_router(account.router, responses=error_handlers.AUTHN_RESPONSES)
router.include_router(invites.router, responses=error_handlers.AUTHN_RESPONSES)
router.include_router(signup.router, responses=error_handlers.AUTHN_RESPONSES)
router.include_router(platform.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(tenants.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(workspaces.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(subscriptions.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(saas_payments.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(audit.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(patients.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(communications.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(scheduling.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(encounters.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(prescriptions.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(dental.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(billing.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(inventory.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(staff.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(operations.router, responses=error_handlers.AUTHZ_RESPONSES)
router.include_router(portal.router, responses=error_handlers.AUTHZ_RESPONSES)
