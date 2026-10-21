"""Module 5-9: hotels, approval, amenities, room types and rooms."""


HOTEL = {"name": "Hill Top", "address_line": "Main Road", "city": "Ooty", "star_rating": 3}


def test_owner_creates_hotel_pending(client, owner):
    r = client.post("/hotels", headers=owner, json=HOTEL)
    assert r.status_code == 201
    assert r.json()["status"] == "PENDING"
    # guests can't see it until admin approves
    assert client.get(f"/hotels/{r.json()['id']}").status_code == 404


def test_customer_cannot_create_hotel(client, customer):
    assert client.post("/hotels", headers=customer, json=HOTEL).status_code == 403


def test_admin_approves_hotel(client, owner, admin):
    hotel_id = client.post("/hotels", headers=owner, json=HOTEL).json()["id"]

    assert client.patch(f"/hotels/{hotel_id}/verify", headers=owner, json={"status": "APPROVED"}).status_code == 403
    r = client.patch(f"/hotels/{hotel_id}/verify", headers=admin, json={"status": "APPROVED"})
    assert r.status_code == 200
    assert client.get(f"/hotels/{hotel_id}").status_code == 200


def test_reject_needs_reason(client, owner, admin):
    hotel_id = client.post("/hotels", headers=owner, json=HOTEL).json()["id"]
    r = client.patch(f"/hotels/{hotel_id}/verify", headers=admin, json={"status": "REJECTED"})
    assert r.status_code == 400


def test_other_owner_cannot_edit(client, api, hotel):
    other = api.register("other@test.com", "HOTEL_OWNER")
    r = client.put(f"/hotels/{hotel['id']}", headers=other, json={"description": "mine now"})
    assert r.status_code == 403


def test_free_owner_limited_to_one_hotel(client, owner, hotel):
    # no subscription = 1 hotel only
    r = client.post("/hotels", headers=owner, json=HOTEL)
    assert r.status_code in (402, 403)


def test_amenities(client, owner, hotel):
    amenities = client.get("/amenities").json()
    assert len(amenities) >= 5
    ids = [a["id"] for a in amenities[:3]]
    r = client.put(f"/hotels/{hotel['id']}/amenities", headers=owner, json={"amenity_ids": ids})
    assert r.status_code == 200
    assert len(r.json()["amenities"]) == 3


def test_room_type_validation(client, owner, hotel):
    r = client.post(f"/hotels/{hotel['id']}/room-types", headers=owner, json={"name": "Cheap", "base_price": -10})
    assert r.status_code == 422
    r = client.post(f"/hotels/{hotel['id']}/room-types", headers=owner, json={"name": "Deluxe", "base_price": 3500})
    assert r.status_code == 409  # same name already exists


def test_duplicate_room_number(client, owner, hotel):
    r = client.post(f"/hotels/{hotel['id']}/rooms", headers=owner, json={"room_type_id": hotel["type_id"], "room_number": "101"})
    assert r.status_code == 409


def test_room_list_is_private(client, owner, customer, hotel):
    assert client.get(f"/hotels/{hotel['id']}/rooms", headers=customer).status_code == 403
    assert len(client.get(f"/hotels/{hotel['id']}/rooms", headers=owner).json()) == 2


def test_search_by_city(client, hotel):
    r = client.get("/search/hotels?city=goa")
    assert r.status_code == 200
    assert r.json()["total"] == 1
    assert client.get("/search/hotels?city=delhi").json()["total"] == 0
