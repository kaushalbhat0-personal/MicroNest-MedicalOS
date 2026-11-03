"""Billing money authority: Decimal-only, HALF_UP, deterministic totals."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.modules.billing import money, numbering
from app.platform.errors import ValidationError


def test_float_is_rejected_at_boundary() -> None:
    with pytest.raises(ValidationError):
        money.ensure_decimal(0.1, field="amount")
    with pytest.raises(ValidationError):
        money.compute_line_total(quantity=2.5, unit_rate=100)  # type: ignore[arg-type]
    # int / str / Decimal are accepted.
    assert money.ensure_decimal(10) == Decimal(10)
    assert money.ensure_decimal("19.99") == Decimal("19.99")
    assert money.ensure_decimal(Decimal("3.5")) == Decimal("3.5")


def test_half_up_rounding_boundaries() -> None:
    # ROUND_HALF_UP differs from banker's rounding exactly here.
    assert money.quantize_half_up(Decimal("2.345")) == Decimal("2.35")
    assert money.quantize_half_up(Decimal("2.335")) == Decimal("2.34")
    assert money.quantize_half_up(Decimal("2.344")) == Decimal("2.34")
    # 0.1 + 0.2 has no drift under Decimal.
    assert money.ensure_decimal("0.1") + money.ensure_decimal("0.2") == Decimal("0.3")


def test_line_calculation_order() -> None:
    # 2 × 100 = 200 gross; −10 discount → 190 taxable; 18% → 34.20; total 224.20.
    out = money.compute_line_total(
        quantity=2, unit_rate="100", discount_amount="10", tax_rate_percent="18"
    )
    assert out["taxable_amount"] == Decimal("190.00")
    assert out["tax_amount"] == Decimal("34.20")
    assert out["line_total"] == Decimal("224.20")


def test_line_guards() -> None:
    with pytest.raises(ValidationError):
        money.compute_line_total(quantity=0, unit_rate=100)
    with pytest.raises(ValidationError):
        money.compute_line_total(quantity=1, unit_rate=-5)
    with pytest.raises(ValidationError):
        money.compute_line_total(quantity=1, unit_rate=100, discount_amount=150)
    with pytest.raises(ValidationError):
        money.compute_line_total(quantity=1, unit_rate=100, tax_rate_percent=-1)


def test_invoice_total_is_sum_of_lines() -> None:
    assert money.compute_invoice_total(["224.20", "100.00", 0]) == Decimal("324.20")
    assert money.compute_invoice_total([]) == Decimal("0.00")
    with pytest.raises(ValidationError):
        money.validate_currency("USD")
    assert money.validate_currency("INR") == "INR"


def test_financial_year_boundaries() -> None:
    assert numbering.fy_for(date(2026, 4, 1)) == "FY2026-27"
    assert numbering.fy_for(date(2027, 3, 31)) == "FY2026-27"
    assert numbering.fy_for(date(2027, 4, 1)) == "FY2027-28"
    assert numbering.validate_fy("FY2026-27") == "FY2026-27"
    with pytest.raises(ValidationError):
        numbering.validate_fy("2026-27")
    with pytest.raises(ValidationError):
        numbering.validate_fy("FY2026-28")
    with pytest.raises(ValidationError):
        numbering.validate_doc_type("voucher")
