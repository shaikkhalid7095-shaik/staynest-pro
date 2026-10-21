"""Plain unit tests for helper functions - no API, no database."""

from decimal import Decimal

from app.services import loyalty_service, pricing_service
from app.services.location_service import distance_km


def test_gst_slabs():
    assert pricing_service.tax_rate_for(Decimal("7500")) == Decimal("0.12")
    assert pricing_service.tax_rate_for(Decimal("7500.01")) == Decimal("0.18")


def test_calculate_with_discount():
    result = pricing_service.calculate(Decimal("10000"), 2, Decimal("1000"))
    # 5000/night -> 12% on (10000 - 1000)
    assert result["tax_amount"] == Decimal("1080.00")
    assert result["total_amount"] == Decimal("10080.00")


def test_loyalty_tiers():
    assert loyalty_service.tier_for(0) == "SILVER"
    assert loyalty_service.tier_for(1000) == "GOLD"
    assert loyalty_service.tier_for(5000) == "PLATINUM"


def test_distance_hyderabad_to_bangalore():
    km = distance_km(17.3850, 78.4867, 12.9716, 77.5946)
    assert 490 < km < 510


def test_distance_same_point():
    assert distance_km(15.0, 73.0, 15.0, 73.0) == 0
