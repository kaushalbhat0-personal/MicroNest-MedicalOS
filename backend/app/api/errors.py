"""RFC-7807 error envelope. Domain errors map to codes; unexpected errors
are generic 500s (details in server logs only — never leak internals).
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.platform.errors import DomainError
from app.platform.logging_setup import get_logger
from app.platform.request_context import request_id_ctx

log = get_logger(__name__)


def _envelope(
    *, type: str, title: str, status: int, detail: str
) -> dict[str, object]:
    return {
        "type": type,
        "title": title,
        "status": status,
        "detail": detail,
        "trace_id": request_id_ctx.get(),
    }


async def _domain_handler(request: Request, exc: DomainError) -> JSONResponse:  # type: ignore[type-arg]
    return JSONResponse(
        status_code=exc.status,
        content=_envelope(
            type=f"https://healthcare-os/errors/{exc.code}",
            title=exc.code.replace("_", " "),
            status=exc.status,
            detail=str(exc),
        ),
    )


async def _validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:  # type: ignore[type-arg]
    return JSONResponse(
        status_code=422,
        content=_envelope(
            type="https://healthcare-os/errors/validation-failed",
            title="validation failed",
            status=422,
            detail="request validation failed",
        ),
    )


async def _unexpected_handler(request: Request, exc: Exception) -> JSONResponse:  # type: ignore[type-arg]
    log.exception("unhandled error")
    return JSONResponse(
        status_code=500,
        content=_envelope(
            type="https://healthcare-os/errors/internal",
            title="internal error",
            status=500,
            detail="internal error",
        ),
    )


def register_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, _domain_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, _unexpected_handler)
