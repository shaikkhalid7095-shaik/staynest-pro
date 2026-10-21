from decimal import ROUND_HALF_UP, Decimal

TWO_PLACES = Decimal("0.01")


def money(value) -> Decimal:
    # always round money to 2 decimal places, the way a bill is rounded
    return Decimal(str(value)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def to_paise(value) -> int:
    # Stripe wants the smallest currency unit: Rs 3920.00 -> 392000 paise
    return int(money(value) * 100)