"""Module 25-26 check-in / check-out and module 43 loyalty points."""

from datetime import date, timedelta

TODAY = date.today()


def test_check_in_and_check_out(client, api, customer, owner, hotel):
    booking = api.book(customer, hotel["id"], hotel["type_id"], TODAY, 2)

    r = client.post(f"/bookings/{booking['id']}/check-in", headers=owner)
    assert r.status_code == 200
    assert r.json()["status"] == "CHECKED_IN"

    r = client.post(f"/bookings/{booking['id']}/check-out", headers=owner)
    assert r.status_code == 200
    summary = r.json()
    assert summary["booking"]["status"] == "CHECKED_OUT"
    # 7000 room spend -> 70 points at SILVER
    assert summary["loyalty_points_earned"] == 70


def test_cannot_check_in_early(client, api, customer, owner, hotel):
    booking = api.book(customer, hotel["id"], hotel["type_id"], TODAY + timedelta(days=5))
    assert client.post(f"/bookings/{booking['id']}/check-in", headers=owner).status_code == 400


def test_unpaid_booking_cannot_check_in(client, api, customer, owner, hotel):
    booking = api.book(customer, hotel["id"], hotel["type_id"], TODAY, pay=False)
    assert client.post(f"/bookings/{booking['id']}/check-in", headers=owner).status_code == 400


def test_loyalty_summary_and_redeem(client, api, customer, owner, admin, hotel):
    booking = api.book(customer, hotel["id"], hotel["type_id"], TODAY, 2)
    client.post(f"/bookings/{booking['id']}/check-in", headers=owner)
    client.post(f"/bookings/{booking['id']}/check-out", headers=owner)

    me = client.get("/loyalty/me", headers=customer).json()
    assert me["points"] == 70
    assert me["tier"] == "SILVER"
    assert me["next_tier"] == "GOLD"

    # less than the minimum
    assert client.post("/loyalty/redeem", headers=customer, json={"points": 50}).status_code == 400

    customer_id = client.get("/auth/me", headers=customer).json()["id"]
    r = client.post("/admin/loyalty/adjust", headers=admin, json={"user_id": customer_id, "points": 1000, "note": "Welcome bonus"})
    assert r.json()["tier"] == "GOLD"

    r = client.post("/loyalty/redeem", headers=customer, json={"points": 200})
    assert r.status_code == 200
    assert r.json()["coupon_code"].startswith("LOYAL-")
    assert r.json()["points_left"] == 870


def test_only_admin_can_adjust_points(client, owner):
    r = client.post("/admin/loyalty/adjust", headers=owner, json={"user_id": 1, "points": 10, "note": "free points"})
    assert r.status_code == 403
