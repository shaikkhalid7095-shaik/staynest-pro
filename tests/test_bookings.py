"""Module 10-16: booking rules, GST, overlap, payments, cancellation."""

from datetime import date, timedelta

NEXT_WEEK = date.today() + timedelta(days=7)


def test_booking_price_with_12_percent_gst(client, api, customer, hotel):
    r = client.post("/bookings", headers=customer, json=api.booking_body(hotel["id"], hotel["type_id"], NEXT_WEEK, 2))
    assert r.status_code == 201
    b = r.json()
    assert b["status"] == "PENDING_PAYMENT"
    # 2 nights x 3500 = 7000, rate is under 7500 so GST is 12%
    assert b["subtotal"] == "7000.00"
    assert b["tax_amount"] == "840.00"
    assert b["total_amount"] == "7840.00"


def test_booking_price_with_18_percent_gst(client, api, owner, admin, customer):
    hotel_id, type_id = api.make_hotel(owner, admin, name="Lux Palace", price=9000, rooms=1)
    b = client.post("/bookings", headers=customer, json=api.booking_body(hotel_id, type_id, NEXT_WEEK, 1)).json()
    assert b["tax_amount"] == "1620.00"  # 18% of 9000
    assert b["total_amount"] == "10620.00"


def test_dates_must_be_valid(client, api, customer, hotel):
    past = api.booking_body(hotel["id"], hotel["type_id"], date.today() - timedelta(days=1))
    assert client.post("/bookings", headers=customer, json=past).status_code == 422

    same_day = api.booking_body(hotel["id"], hotel["type_id"], NEXT_WEEK, 0)
    assert client.post("/bookings", headers=customer, json=same_day).status_code == 422


def test_too_many_guests(client, api, customer, hotel):
    body = api.booking_body(hotel["id"], hotel["type_id"], NEXT_WEEK, adults=3)
    assert client.post("/bookings", headers=customer, json=body).status_code == 400


def test_owner_cannot_book(client, api, owner, hotel):
    body = api.booking_body(hotel["id"], hotel["type_id"], NEXT_WEEK)
    assert client.post("/bookings", headers=owner, json=body).status_code == 403


def test_no_double_booking(client, api, customer, hotel):
    other = api.register("second@test.com")
    third = api.register("third@test.com")
    body = api.booking_body(hotel["id"], hotel["type_id"], NEXT_WEEK, 2)

    # the hotel has 2 rooms
    assert client.post("/bookings", headers=customer, json=body).status_code == 201
    assert client.post("/bookings", headers=other, json=body).status_code == 201
    assert client.post("/bookings", headers=third, json=body).status_code == 409

    # starting on the check-out day is fine
    back_to_back = api.booking_body(hotel["id"], hotel["type_id"], NEXT_WEEK + timedelta(days=2), 1)
    assert client.post("/bookings", headers=third, json=back_to_back).status_code == 201


def test_customers_see_only_their_bookings(client, api, customer, owner, hotel):
    booking = api.book(customer, hotel["id"], hotel["type_id"], NEXT_WEEK, pay=False)
    stranger = api.register("stranger@test.com")

    assert client.get(f"/bookings/{booking['id']}", headers=stranger).status_code == 403
    assert client.get(f"/bookings/{booking['id']}", headers=owner).status_code == 200
    assert len(client.get("/bookings/my", headers=customer).json()) == 1


def test_payment_confirms_booking_and_makes_invoice(client, api, customer, hotel):
    booking = api.book(customer, hotel["id"], hotel["type_id"], NEXT_WEEK, pay=False)
    assert client.get(f"/bookings/{booking['id']}/invoice", headers=customer).status_code == 404

    p1 = client.post("/payments/create-intent", headers=customer, json={"booking_id": booking["id"]}).json()
    p2 = client.post("/payments/create-intent", headers=customer, json={"booking_id": booking["id"]}).json()
    assert p1["payment_id"] == p2["payment_id"]  # no duplicate payment
    assert p1["amount"] == "7840.00"

    r = client.post(f"/payments/{p1['payment_id']}/test-confirm", headers=customer)
    assert r.json()["booking_status"] == "CONFIRMED"
    assert client.get(f"/bookings/{booking['id']}/invoice", headers=customer).status_code == 200


def test_cancel_early_gives_full_refund(client, api, customer, hotel):
    booking = api.book(customer, hotel["id"], hotel["type_id"], NEXT_WEEK)

    quote = client.get(f"/bookings/{booking['id']}/refund-quote", headers=customer).json()
    assert quote["refund_percent"] == 100

    r = client.post(f"/bookings/{booking['id']}/cancel", headers=customer, json={"reason": "Plans changed"})
    assert r.status_code == 200
    assert r.json()["booking"]["status"] == "CANCELLED"
    assert r.json()["refund_amount"] == "7840.00"

    # can't cancel twice
    assert client.post(f"/bookings/{booking['id']}/cancel", headers=customer, json={}).status_code == 400


def test_cancelled_room_is_free_again(client, api, customer, hotel):
    other = api.register("second@test.com")
    third = api.register("third@test.com")
    body = api.booking_body(hotel["id"], hotel["type_id"], NEXT_WEEK)
    first = client.post("/bookings", headers=customer, json=body).json()
    client.post("/bookings", headers=other, json=body)
    assert client.post("/bookings", headers=third, json=body).status_code == 409

    client.post(f"/bookings/{first['id']}/cancel", headers=customer, json={})
    assert client.post("/bookings", headers=third, json=body).status_code == 201
