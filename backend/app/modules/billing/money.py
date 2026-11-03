"""Billing money authority. Single source of truth for monetary arithmetic.

Decimal only — float is rejected at the boundary. ROUND_HALF_UP to paise.
Deterministic order per P4-01 §3: quantity × unit_rate → discount →
taxable → tax → line total; invoice = sum(line totals).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.platform.errors import ValidationError

PAISE = Decimal("0.01")
INR = "INR"


def ensure_decimal(value: object, *, field: str = "amount") -> Decimal:
    """Coerce int/str/Decimal to Decimal. Floats are rejected outright —
    silently accepting binary floating point into money is a defect."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValidationError(f"{field} must be Decimal, int or numeric string (float forbidden)")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError(f"{field} is not a valid decimal") from exc
    if not result.is_finite():
        raise ValidationError(f"{field} must be finite")
    return result


def quantize_half_up(value: Decimal) -> Decimal:
    """Round to paise with ROUND_HALF_UP. The only rounding function."""
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)


def validate_currency(code: str | None) -> str:
    """P4 MVP is INR-only. The column exists so multi-currency is later a
    policy change, not a schema migration."""
    if code != INR:
        raise ValidationError("only INR is supported in P4")
    return INR


def compute_line_total(
    *,
    quantity: object,
    unit_rate: object,
    discount_amount: object = 0,
    tax_rate_percent: object = 0,
) -> dict[str, Decimal]:
    """Deterministic line math. No intermediate rounding inside
    quantity × rate; quantization at taxable/tax/total boundaries only."""
    qty = ensure_decimal(quantity, field="quantity")
    rate = ensure_decimal(unit_rate, field="unit_rate")
    discount = ensure_decimal(discount_amount, field="discount_amount")
    tax_rate = ensure_decimal(tax_rate_percent, field="tax_rate")
    if qty <= 0:
        raise ValidationError("quantity must be positive")
    if rate < 0 or discount < 0 or tax_rate < 0:
        raise ValidationError("rate, discount and tax rate must be non-negative")
    gross = qty * rate
    if discount > gross:
        raise ValidationError("discount cannot exceed gross amount")
    taxable = quantize_half_up(gross - discount)
    tax_amount = quantize_half_up(taxable * tax_rate / Decimal(100))
    return {
        "taxable_amount": taxable,
        "tax_amount": tax_amount,
        "line_total": quantize_half_up(taxable + tax_amount),
    }


def compute_invoice_total(line_totals: list[object]) -> Decimal:
    """Invoice total = sum of stored line totals, quantized once."""
    total = sum((ensure_decimal(t, field="line_total") for t in line_totals), Decimal(0))
    if total < 0:
        raise ValidationError("invoice total must be non-negative")
    return quantize_half_up(total)
