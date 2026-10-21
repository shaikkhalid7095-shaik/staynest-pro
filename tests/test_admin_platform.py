"""Day 4 modules: dashboards, analytics, reports, fraud, audit, settings, finance, admin."""

from datetime import date, timedelta

TODAY = date.today()


def test_dashboards_by_role(client, admin, owner, customer, hotel):
    assert client.get("/dashboard/admin", headers=admin).status_code == 200
    assert client.get("/dashboard/owner", headers=owner).status_code == 200
    assert client.get("/dashboard/customer", headers=customer).status_code == 200
    # wrong role
    assert client.get("/dashboard/admin", headers=owner).status_code == 403


def test_occupancy_numbers(client, api, customer, owner, hotel):
    # 1 of 2 rooms booked for 2 nights, looking at those 2 days only
    api.book(customer, hotel["id"], hotel["type_id"], TODAY, 2)
    end = TODAY + timedelta(days=1)
    r = client.get(f"/analytics/occupancy?hotel_id={hotel['id']}&start={TODAY}&end={end}", headers=owner)
    data = r.json()
    assert data["room_nights_sold"] == 2
    assert data["room_nights_available"] == 4
    assert data["occupancy_percent"] == 50.0


def test_owner_cannot_see_other_hotels_analytics(client, api, hotel):
    other = api.register("other@test.com", "HOTEL_OWNER")
    r = client.get(f"/analytics/revenue?hotel_id={hotel['id']}", headers=other)
    assert r.status_code == 403


def test_bookings_csv_export(client, api, customer, owner, hotel):
    api.book(customer, hotel["id"], hotel["type_id"], TODAY + timedelta(days=3))
    r = client.get("/reports/bookings.csv", headers=owner, params={"end": str(TODAY + timedelta(days=10))})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    lines = r.text.strip().splitlines()
    assert lines[0].startswith("booking_code,hotel")
    assert len(lines) == 2


def test_fraud_flag_for_many_bookings(client, api, customer, admin, hotel):
    for i in range(4):
        api.book(customer, hotel["id"], hotel["type_id"], TODAY + timedelta(days=20 + i * 3), 1, pay=False)

    flags = client.get("/admin/fraud/flags", headers=admin).json()
    assert len(flags) == 1
    assert "bookings in the last hour" in flags[0]["reasons"]

    r = client.patch(f"/admin/fraud/flags/{flags[0]['id']}", headers=admin, json={"status": "DISMISSED", "note": "Family trip"})
    assert r.json()["status"] == "DISMISSED"
    assert client.get("/admin/fraud/flags", headers=admin).json() == []


def test_audit_log_records_logins(client, admin, customer):
    client.post("/auth/login", data={"username": "guest@test.com", "password": "wrong-pass"})
    logs = client.get("/admin/audit-logs?action=LOGIN_FAILED", headers=admin).json()
    assert len(logs) == 1
    assert logs[0]["details"] == "guest@test.com"


def test_settings_change_is_used(client, api, admin, customer):
    r = client.put("/admin/settings/max_failed_logins", headers=admin, json={"value": "2"})
    assert r.status_code == 200
    assert r.json()["value"] == "2"

    for _ in range(2):
        client.post("/auth/login", data={"username": "guest@test.com", "password": "wrong-pass"})
    assert client.post("/auth/login", data={"username": "guest@test.com", "password": "secret123"}).status_code == 429


def test_settings_validation(client, admin):
    assert client.put("/admin/settings/max_failed_logins", headers=admin, json={"value": "abc"}).status_code == 422
    assert client.put("/admin/settings/no_such_key", headers=admin, json={"value": "1"}).status_code == 404


def test_public_settings_hide_private_values(client):
    data = client.get("/settings/public").json()
    assert data["platform_name"] == "StayNest Pro"
    assert "platform_commission_percent" not in data


def test_block_user(client, api, admin, customer):
    customer_id = client.get("/auth/me", headers=customer).json()["id"]
    r = client.patch(f"/admin/users/{customer_id}/status", headers=admin, json={"is_active": False, "reason": "Spam"})
    assert r.status_code == 200

    r = client.post("/auth/login", data={"username": "guest@test.com", "password": "secret123"})
    assert r.status_code == 403
    # old access token stops working too
    assert client.get("/auth/me", headers=customer).status_code == 401


def test_admin_cannot_block_self(client, admin):
    admin_id = client.get("/auth/me", headers=admin).json()["id"]
    r = client.patch(f"/admin/users/{admin_id}/status", headers=admin, json={"is_active": False})
    assert r.status_code == 400


def test_suspend_and_reinstate_hotel(client, admin, hotel):
    assert client.post(f"/admin/hotels/{hotel['id']}/suspend", headers=admin, json={}).status_code == 400  # no reason
    r = client.post(f"/admin/hotels/{hotel['id']}/suspend", headers=admin, json={"reason": "Fake photos"})
    assert r.json()["status"] == "SUSPENDED"
    assert client.get(f"/hotels/{hotel['id']}").status_code == 404

    r = client.post(f"/admin/hotels/{hotel['id']}/reinstate", headers=admin)
    assert r.json()["status"] == "APPROVED"


def test_finance_summary_after_checkout(client, api, customer, owner, hotel):
    booking = api.book(customer, hotel["id"], hotel["type_id"], TODAY, 2)
    client.post(f"/bookings/{booking['id']}/check-in", headers=owner)
    client.post(f"/bookings/{booking['id']}/check-out", headers=owner)

    r = client.get(f"/finance/hotels/{hotel['id']}/summary?start={TODAY}&end={TODAY + timedelta(days=5)}", headers=owner)
    data = r.json()
    # guest paid 7840, platform keeps 10% of 7000 (plain dicts send money as numbers)
    assert data["gross_amount"] == 7840
    assert data["commission_amount"] == 700
    assert data["net_payable"] == 7140


def test_payout_period_must_be_finished(client, admin, hotel):
    body = {"hotel_id": hotel["id"], "period_start": str(TODAY), "period_end": str(TODAY)}
    assert client.post("/admin/payouts", headers=admin, json=body).status_code == 400


def test_nearby_hotels(client, api, owner, admin):
    api.make_hotel(owner, admin, name="Beach Hut", lat=15.5527, lng=73.7517)
    r = client.get("/locations/nearby?lat=15.4989&lng=73.8278&radius_km=15")
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert 5 < r.json()[0]["distance_km"] < 15


def test_system_health(client, admin):
    data = client.get("/admin/system/health", headers=admin).json()
    assert data["database"] == "connected"
