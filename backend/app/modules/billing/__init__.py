"""Billing foundation (P4.1): persistence + money/numbering authorities.

Billing owns monetary truth; no floats, ever. Issued documents are immutable
snapshots; patient credit is derived from allocations, never a ledger table.
Services/routers for estimates/invoices/payments land in P4.2+; this package
holds models, money math, and numbering helpers only."""

from app.modules.billing import models  # noqa: F401
