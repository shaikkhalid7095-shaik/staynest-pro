import secrets
from types import SimpleNamespace

_intents = {}


def _new_id(prefix):
    return f"{prefix}_mock_{secrets.token_hex(8)}"


class PaymentIntent:
    @staticmethod
    def create(amount, currency="inr", idempotency_key=None, **kwargs):
        for intent in _intents.values():
            if idempotency_key and intent.idempotency_key == idempotency_key:
                return intent
        intent_id = _new_id("pi")
        intent = SimpleNamespace(
            id=intent_id, client_secret=intent_id + "_secret", amount=amount, currency=currency,
            status="requires_payment_method", metadata=kwargs.get("metadata", {}),
            idempotency_key=idempotency_key,
        )
        _intents[intent_id] = intent
        return intent

    @staticmethod
    def retrieve(intent_id):
        if intent_id not in _intents:
            _intents[intent_id] = SimpleNamespace(
                id=intent_id, client_secret=intent_id + "_secret",
                status="requires_payment_method", idempotency_key=None,
            )
        return _intents[intent_id]

    @staticmethod
    def confirm(intent_id, payment_method=None):
        intent = PaymentIntent.retrieve(intent_id)
        intent.status = "succeeded"
        return intent


class Refund:
    @staticmethod
    def create(payment_intent=None, amount=None, **kwargs):
        return SimpleNamespace(id=_new_id("re"), status="succeeded", amount=amount, payment_intent=payment_intent)
