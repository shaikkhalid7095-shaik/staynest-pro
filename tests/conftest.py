"""Shared setup for all tests.

Tests never touch MySQL or the real Stripe. Every test gets a fresh
in-memory SQLite database with the seed data (roles, amenities, plans,
admin user), and Stripe calls are replaced with small fakes.
"""

import os

# must be set before anything from app/ is imported
os.environ.update(
    SECRET_KEY="test-secret-key-1234567890-abcdef",
    STRIPE_SECRET_KEY="sk_test_fake",
    STRIPE_WEBHOOK_SECRET="whsec_test",
    ANTHROPIC_API_KEY="",
    DEBUG="True",
)
os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("DB_NAME", "test")

from datetime import date, timedelta
from types import SimpleNamespace

import pytest
import stripe
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.db.seed as seed_module
import app.models  # noqa: F401 - registers every table on Base
from app.core.deps import get_db
from app.db.base import Base
from app.main import app

PASSWORD = "secret123"
ADMIN_EMAIL = "admin@staynest.com"
ADMIN_PASSWORD = "Admin@12345"


# ---------- database ----------

@pytest.fixture
def db_session_factory(monkeypatch):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    monkeypatch.setattr(seed_module, "SessionLocal", TestSession)
    seed_module.seed()

    def override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestSession
    app.dependency_overrides.clear()
    engine.dispose()


# ---------- fake stripe ----------

@pytest.fixture(autouse=True)
def fake_stripe(monkeypatch):
    intents = {}

    def create_intent(**kwargs):
        # same idempotency key -> same intent, just like real Stripe
        for intent in intents.values():
            if intent.key == kwargs.get("idempotency_key"):
                return intent
        n = len(intents) + 1
        intent = SimpleNamespace(id=f"pi_test_{n}", client_secret=f"pi_test_{n}_secret",
                                 status="requires_payment_method", amount=kwargs["amount"],
                                 key=kwargs.get("idempotency_key"))
        intents[intent.id] = intent
        return intent

    def confirm_intent(intent_id, payment_method=None):
        intents[intent_id].status = "succeeded"
        return intents[intent_id]

    def create_refund(**kwargs):
        return SimpleNamespace(id=f"re_test_{len(intents)}", status="succeeded")

    monkeypatch.setattr(stripe.PaymentIntent, "create", staticmethod(create_intent))
    monkeypatch.setattr(stripe.PaymentIntent, "retrieve", staticmethod(lambda intent_id: intents[intent_id]))
    monkeypatch.setattr(stripe.PaymentIntent, "confirm", staticmethod(confirm_intent))
    monkeypatch.setattr(stripe.Refund, "create", staticmethod(create_refund))
    return intents


# ---------- client + helpers ----------

class Api:
    """Small wrapper so tests read like steps: api.register(...), api.book(...)"""

    def __init__(self, client: TestClient):
        self.client = client

    def login(self, email: str, password: str = PASSWORD) -> dict:
        r = self.client.post("/auth/login", data={"username": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}

    def register(self, email: str, role: str = "CUSTOMER", name: str = "Test User") -> dict:
        r = self.client.post("/auth/register", json={"email": email, "password": PASSWORD, "full_name": name, "role": role})
        assert r.status_code == 201, r.text
        return self.login(email)

    def make_hotel(self, owner: dict, admin: dict, name="Sea View", city="Goa", price=3500, rooms=2,
                   lat=None, lng=None) -> tuple[int, int]:
        body = {"name": name, "address_line": "Beach Road", "city": city, "star_rating": 4}
        if lat is not None:
            body.update(latitude=lat, longitude=lng)
        r = self.client.post("/hotels", headers=owner, json=body)
        assert r.status_code == 201, r.text
        hotel_id = r.json()["id"]

        r = self.client.patch(f"/hotels/{hotel_id}/verify", headers=admin, json={"status": "APPROVED"})
        assert r.status_code == 200, r.text

        r = self.client.post(f"/hotels/{hotel_id}/room-types", headers=owner,
                             json={"name": "Deluxe", "base_price": price, "max_adults": 2, "max_children": 1})
        assert r.status_code == 201, r.text
        type_id = r.json()["id"]

        for n in range(rooms):
            r = self.client.post(f"/hotels/{hotel_id}/rooms", headers=owner,
                                 json={"room_type_id": type_id, "room_number": str(101 + n)})
            assert r.status_code == 201, r.text
        return hotel_id, type_id

    def booking_body(self, hotel_id: int, type_id: int, check_in: date, nights: int = 2, **extra) -> dict:
        return {"hotel_id": hotel_id, "room_type_id": type_id, "check_in": str(check_in),
                "check_out": str(check_in + timedelta(days=nights)), "adults": 1, **extra}

    def book(self, customer: dict, hotel_id: int, type_id: int, check_in: date, nights: int = 2, pay: bool = True) -> dict:
        r = self.client.post("/bookings", headers=customer, json=self.booking_body(hotel_id, type_id, check_in, nights))
        assert r.status_code == 201, r.text
        booking = r.json()
        if pay:
            p = self.client.post("/payments/create-intent", headers=customer, json={"booking_id": booking["id"]})
            assert p.status_code == 200, p.text
            c = self.client.post(f"/payments/{p.json()['payment_id']}/test-confirm", headers=customer)
            assert c.status_code == 200, c.text
            assert c.json()["booking_status"] == "CONFIRMED"
        return booking


@pytest.fixture
def client(db_session_factory):
    with TestClient(app) as c:
        yield c


@pytest.fixture
def api(client):
    return Api(client)


@pytest.fixture
def admin(api):
    return api.login(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.fixture
def owner(api):
    return api.register("owner@test.com", "HOTEL_OWNER", "Owner One")


@pytest.fixture
def customer(api):
    return api.register("guest@test.com", "CUSTOMER", "Guest One")


@pytest.fixture
def hotel(api, owner, admin):
    """An approved hotel in Goa with one room type (Rs 3500/night) and 2 rooms."""
    hotel_id, type_id = api.make_hotel(owner, admin)
    return {"id": hotel_id, "type_id": type_id}
