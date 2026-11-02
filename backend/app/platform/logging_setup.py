"""PHI/secret scrubbing for logs and spans.

Any log record (message or args) passing through the platform logger is
scrubbed for known-sensitive keys AND known-sensitive value patterns.
Tests assert that passwords, tokens, OTPs, and clinical payload keys never
survive. When in doubt, add the key to SENSITIVE_KEYS — over-redaction of
debug logs is acceptable, under-redaction is a release blocker.
"""

import copy
import logging
import re
from typing import Any

SENSITIVE_KEYS = frozenset(
    {
        "password",
        "passwd",
        "pwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "otp",
        "authorization",
        "cookie",
        "set-cookie",
        "api_key",
        "apikey",
        "private_key",
        "decryption_key",
        # Clinical — never in logs by design; scrubbed if leaked.
        "clinical_note",
        "clinical_notes",
        "subjective",
        "objective",
        "assessment",
        "plan_notes",
        "diagnosis",
        "diagnoses",
        "prescription",
        "medication",
        "image",
        "image_bytes",
    }
)

# Bearer tokens / JWT-shaped values anywhere in free text.
_TOKEN_RE = re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")


def scrub(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and k.lower() in SENSITIVE_KEYS:
                out[k] = "[REDACTED]"
            else:
                out[k] = scrub(v)
        return out
    if isinstance(obj, list | tuple):
        return [scrub(v) for v in obj]
    if isinstance(obj, str):
        return _TOKEN_RE.sub("[REDACTED-TOKEN]", obj)
    return copy.deepcopy(obj) if isinstance(obj, dict | list) else obj


class ScrubbingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, dict):
            record.msg = scrub(record.msg)  # type: ignore[assignment]
        elif isinstance(record.msg, str):
            record.msg = _TOKEN_RE.sub("[REDACTED-TOKEN]", record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = scrub(record.args)  # type: ignore[assignment]
            elif isinstance(record.args, tuple):
                record.args = tuple(scrub(a) for a in record.args)  # type: ignore[assignment]
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not any(isinstance(f, ScrubbingFilter) for f in logger.filters):
        logger.addFilter(ScrubbingFilter())
    return logger


class RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        from app.platform.request_context import request_id_ctx

        record.request_id = request_id_ctx.get()
        return True


def configure_root_logging(level: int = logging.INFO) -> None:
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] request_id=%(request_id)s %(message)s"
            )
        )
        handler.addFilter(RequestIDFilter())
        handler.addFilter(ScrubbingFilter())
        root.addHandler(handler)
        root.setLevel(level)
    if not any(isinstance(f, RequestIDFilter) for f in root.filters):
        root.addFilter(RequestIDFilter())
    if not any(isinstance(f, ScrubbingFilter) for f in root.filters):
        root.addFilter(ScrubbingFilter())
