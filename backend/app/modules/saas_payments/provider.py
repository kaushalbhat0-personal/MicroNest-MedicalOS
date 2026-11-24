"""Payment provider adapters for SaaS subscription charges.

Razorpay is the production target (INR / India). A ``mock`` adapter supports
offline tests with HMAC-signed webhook bodies — same verification contract.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from app.platform.config import get_settings
from app.platform.errors import ForbiddenError, ServiceUnavailableError, ValidationError


@dataclass(frozen=True)
class CheckoutOrder:
    provider: str
    order_id: str
    amount_minor: int
    currency: str
    public_key: str | None
    checkout_hint: dict[str, Any]


@dataclass(frozen=True)
class NormalizedProviderEvent:
    provider: str
    event_id: str
    event_type: str  # payment.captured | payment.failed | refund.processed | payment.dispute
    provider_order_id: str | None
    provider_payment_id: str | None
    amount_minor: int | None
    currency: str | None
    occurred_at_epoch: int | None
    raw_digest: str
    refund_amount_minor: int | None = None


class PaymentProvider(Protocol):
    name: str

    def create_customer(self, *, tenant_id: uuid.UUID, email: str | None) -> str: ...

    def create_order(
        self,
        *,
        amount_minor: int,
        currency: str,
        receipt: str,
        notes: dict[str, str],
    ) -> CheckoutOrder: ...

    def verify_webhook(self, *, raw_body: bytes, signature: str | None) -> None: ...

    def parse_webhook(self, *, raw_body: bytes) -> NormalizedProviderEvent: ...

    def fetch_payment_status(self, *, provider_payment_id: str) -> dict[str, Any]: ...

    def assert_environment(self) -> None: ...


def _digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _hmac_match(secret: bytes, raw_body: bytes, signature: str) -> bool:
    expected = hmac.new(secret, raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


class MockProvider:
    """Deterministic sandbox stand-in. No network. HMAC over raw body."""

    name = "mock"

    def __init__(
        self,
        *,
        webhook_secret: str,
        webhook_secret_previous: str | None = None,
        public_key: str = "mock_pk_test",
    ) -> None:
        self._secrets = [webhook_secret.encode()]
        if webhook_secret_previous:
            self._secrets.append(webhook_secret_previous.encode())
        self._public_key = public_key

    def assert_environment(self) -> None:
        return

    def create_customer(self, *, tenant_id: uuid.UUID, email: str | None) -> str:
        return f"cust_mock_{tenant_id.hex[:16]}"

    def create_order(
        self,
        *,
        amount_minor: int,
        currency: str,
        receipt: str,
        notes: dict[str, str],
    ) -> CheckoutOrder:
        order_id = f"order_mock_{hashlib.sha256(receipt.encode()).hexdigest()[:16]}"
        return CheckoutOrder(
            provider=self.name,
            order_id=order_id,
            amount_minor=amount_minor,
            currency=currency,
            public_key=self._public_key,
            checkout_hint={
                "mode": "mock",
                "receipt": receipt,
                "notes": notes,
                "message": "POST a signed mock webhook to complete payment",
            },
        )

    def verify_webhook(self, *, raw_body: bytes, signature: str | None) -> None:
        if not signature:
            raise ForbiddenError("missing webhook signature")
        if not any(_hmac_match(secret, raw_body, signature) for secret in self._secrets):
            raise ForbiddenError("invalid webhook signature")

    def parse_webhook(self, *, raw_body: bytes) -> NormalizedProviderEvent:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("invalid webhook JSON") from exc
        event_id = str(payload.get("id") or "")
        event_type = str(payload.get("event") or "")
        if not event_id or not event_type:
            raise ValidationError("webhook missing id/event")
        payment = (payload.get("payload") or {}).get("payment", {}).get("entity") or {}
        refund = (payload.get("payload") or {}).get("refund", {}).get("entity") or {}
        mapped = event_type
        if event_type in ("payment.captured", "order.paid"):
            mapped = "payment.captured"
        elif event_type == "payment.failed":
            mapped = "payment.failed"
        elif event_type in ("refund.processed", "refund.created"):
            mapped = "refund.processed"
        elif event_type.startswith("payment.dispute"):
            mapped = "payment.dispute"
        order_id = payment.get("order_id") or refund.get("payment_id") and payment.get(
            "order_id"
        )
        # Prefer explicit order_id; refunds may only carry payment_id.
        if not order_id:
            order_id = payment.get("order_id") or None
        pay_id = payment.get("id") or refund.get("payment_id") or None
        refund_amt = None
        if mapped == "refund.processed":
            if refund.get("amount") is not None:
                refund_amt = int(refund["amount"])
            elif payload.get("refund_amount_minor") is not None:
                refund_amt = int(payload["refund_amount_minor"])
            elif payment.get("amount_refunded") is not None:
                refund_amt = int(payment["amount_refunded"])
        return NormalizedProviderEvent(
            provider=self.name,
            event_id=event_id,
            event_type=mapped,
            provider_order_id=order_id,
            provider_payment_id=pay_id,
            amount_minor=int(payment["amount"]) if payment.get("amount") is not None else None,
            currency=(payment.get("currency") or refund.get("currency") or None),
            occurred_at_epoch=payment.get("created_at") or refund.get("created_at"),
            raw_digest=_digest(raw_body),
            refund_amount_minor=refund_amt,
        )

    def fetch_payment_status(self, *, provider_payment_id: str) -> dict[str, Any]:
        return {"id": provider_payment_id, "status": "captured", "provider": self.name}


class RazorpayProvider:
    """Razorpay Orders + webhook HMAC (X-Razorpay-Signature).

    Network calls only when key_id/secret are configured. Checkout still
    snapshots amounts server-side; browser return URL is never trusted.
    """

    name = "razorpay"

    def __init__(
        self,
        *,
        key_id: str,
        key_secret: str,
        webhook_secret: str,
        webhook_secret_previous: str | None = None,
    ) -> None:
        if not key_id or not key_secret or not webhook_secret:
            raise ServiceUnavailableError("razorpay is not configured")
        if not key_id.startswith("rzp_test_") and not key_id.startswith("rzp_live_"):
            raise ServiceUnavailableError("razorpay key id format invalid")
        self._key_id = key_id
        self._key_secret = key_secret
        self._secrets = [webhook_secret.encode()]
        if webhook_secret_previous:
            self._secrets.append(webhook_secret_previous.encode())

    def assert_environment(self) -> None:
        # Production must use live keys; non-prod must use test keys.
        settings = get_settings()
        env = (settings.ENV or "dev").lower()
        is_test_key = self._key_id.startswith("rzp_test_")
        if env in ("prod", "production") and is_test_key:
            raise ServiceUnavailableError("production cannot use razorpay test keys")
        if env not in ("prod", "production") and not is_test_key:
            raise ServiceUnavailableError("non-production must use razorpay test keys")

    def create_customer(self, *, tenant_id: uuid.UUID, email: str | None) -> str:
        # Lazy local id until live customer API is required; stored on saas_customers.
        return f"cust_rzp_{tenant_id.hex[:20]}"

    def create_order(
        self,
        *,
        amount_minor: int,
        currency: str,
        receipt: str,
        notes: dict[str, str],
    ) -> CheckoutOrder:
        try:
            import urllib.error
            import urllib.request
            from base64 import b64encode
        except ImportError as exc:  # pragma: no cover
            raise ServiceUnavailableError("urllib unavailable") from exc

        body = json.dumps(
            {
                "amount": amount_minor,
                "currency": currency.upper(),
                "receipt": receipt[:40],
                "notes": notes,
                "payment_capture": 1,
            }
        ).encode()
        auth = b64encode(f"{self._key_id}:{self._key_secret}".encode()).decode()
        req = urllib.request.Request(
            "https://api.razorpay.com/v1/orders",
            data=body,
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            raise ServiceUnavailableError("razorpay order create failed") from exc
        except Exception as exc:  # noqa: BLE001
            raise ServiceUnavailableError("razorpay unreachable") from exc
        return CheckoutOrder(
            provider=self.name,
            order_id=str(data["id"]),
            amount_minor=int(data["amount"]),
            currency=str(data["currency"]).upper(),
            public_key=self._key_id,
            checkout_hint={
                "mode": "razorpay_checkout",
                "order_id": data["id"],
                "key_id": self._key_id,
            },
        )

    def verify_webhook(self, *, raw_body: bytes, signature: str | None) -> None:
        if not signature:
            raise ForbiddenError("missing webhook signature")
        if not any(_hmac_match(secret, raw_body, signature) for secret in self._secrets):
            raise ForbiddenError("invalid webhook signature")

    def parse_webhook(self, *, raw_body: bytes) -> NormalizedProviderEvent:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValidationError("invalid webhook JSON") from exc
        event_id = str(payload.get("event_id") or payload.get("id") or "")
        event_type = str(payload.get("event") or "")
        if not event_type:
            raise ValidationError("webhook missing event")
        if not event_id:
            event_id = f"rzp_{_digest(raw_body)[:32]}"
        payment = (
            (payload.get("payload") or {}).get("payment", {}).get("entity")
            or (payload.get("payload") or {}).get("payment")
            or {}
        )
        refund = (payload.get("payload") or {}).get("refund", {}).get("entity") or {}
        mapped = event_type
        if event_type in ("payment.captured", "order.paid"):
            mapped = "payment.captured"
        elif event_type in ("payment.failed",):
            mapped = "payment.failed"
        elif event_type in ("refund.processed", "refund.created"):
            mapped = "refund.processed"
        elif event_type.startswith("payment.dispute"):
            mapped = "payment.dispute"
        refund_amt = None
        if mapped == "refund.processed" and refund.get("amount") is not None:
            refund_amt = int(refund["amount"])
        elif mapped == "refund.processed" and payment.get("amount_refunded") is not None:
            refund_amt = int(payment["amount_refunded"])
        return NormalizedProviderEvent(
            provider=self.name,
            event_id=event_id,
            event_type=mapped,
            provider_order_id=(payment.get("order_id") or None),
            provider_payment_id=(payment.get("id") or refund.get("payment_id") or None),
            amount_minor=int(payment["amount"]) if payment.get("amount") is not None else None,
            currency=(
                str(payment["currency"]).upper()
                if payment.get("currency")
                else (str(refund["currency"]).upper() if refund.get("currency") else None)
            ),
            occurred_at_epoch=payment.get("created_at") or refund.get("created_at"),
            raw_digest=_digest(raw_body),
            refund_amount_minor=refund_amt,
        )

    def fetch_payment_status(self, *, provider_payment_id: str) -> dict[str, Any]:
        try:
            import urllib.request
            from base64 import b64encode
        except ImportError as exc:  # pragma: no cover
            raise ServiceUnavailableError("urllib unavailable") from exc
        auth = b64encode(f"{self._key_id}:{self._key_secret}".encode()).decode()
        req = urllib.request.Request(
            f"https://api.razorpay.com/v1/payments/{provider_payment_id}",
            headers={"Authorization": f"Basic {auth}"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310
                return json.loads(resp.read().decode())
        except Exception as exc:  # noqa: BLE001
            raise ServiceUnavailableError("razorpay payment fetch failed") from exc


def get_provider() -> PaymentProvider:
    settings = get_settings()
    name = (getattr(settings, "SAAS_PAYMENT_PROVIDER", None) or "mock").strip().lower()
    prev = getattr(settings, "SAAS_PAYMENT_WEBHOOK_SECRET_PREVIOUS", None) or None
    if name == "razorpay":
        provider: PaymentProvider = RazorpayProvider(
            key_id=getattr(settings, "RAZORPAY_KEY_ID", "") or "",
            key_secret=getattr(settings, "RAZORPAY_KEY_SECRET", "") or "",
            webhook_secret=getattr(settings, "RAZORPAY_WEBHOOK_SECRET", "") or "",
            webhook_secret_previous=prev
            or (getattr(settings, "RAZORPAY_WEBHOOK_SECRET_PREVIOUS", None) or None),
        )
        provider.assert_environment()
        return provider
    if name != "mock":
        raise ValidationError("unknown SAAS_PAYMENT_PROVIDER")
    secret = getattr(settings, "SAAS_PAYMENT_WEBHOOK_SECRET", None) or "mock-webhook-secret"
    return MockProvider(webhook_secret=secret, webhook_secret_previous=prev)
