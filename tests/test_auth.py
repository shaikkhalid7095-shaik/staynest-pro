"""Module 1-4: register, login, JWT tokens, roles, password reset, lockout."""

from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, PASSWORD


def test_register_customer(client):
    r = client.post("/auth/register", json={"email": "New@Test.com", "password": PASSWORD, "full_name": "New User"})
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["email"] == "new@test.com"  # stored in lower case
    assert body["user"]["role"] == "CUSTOMER"
    assert body["verification_token"]


def test_register_duplicate_email(client, customer):
    r = client.post("/auth/register", json={"email": "guest@test.com", "password": PASSWORD, "full_name": "Again"})
    assert r.status_code == 409


def test_cannot_register_as_admin(client):
    r = client.post("/auth/register", json={"email": "x@test.com", "password": PASSWORD, "full_name": "Hacker", "role": "ADMIN"})
    assert r.status_code == 422


def test_register_validation(client):
    r = client.post("/auth/register", json={"email": "not-an-email", "password": "1", "full_name": "x"})
    assert r.status_code == 422


def test_login_and_me(client, api):
    headers = api.register("me@test.com")
    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "me@test.com"


def test_login_wrong_password(client, customer):
    r = client.post("/auth/login", data={"username": "guest@test.com", "password": "wrong-pass"})
    assert r.status_code == 401


def test_me_needs_token(client):
    assert client.get("/auth/me").status_code == 401


def test_refresh_token_rotation(client, customer):
    tokens = client.post("/auth/login", data={"username": "guest@test.com", "password": PASSWORD}).json()

    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    # the old refresh token is now used up
    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 401


def test_refresh_token_is_not_an_access_token(client, customer):
    tokens = client.post("/auth/login", data={"username": "guest@test.com", "password": PASSWORD}).json()
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {tokens['refresh_token']}"})
    assert r.status_code == 401


def test_logout(client, customer):
    tokens = client.post("/auth/login", data={"username": "guest@test.com", "password": PASSWORD}).json()
    assert client.post("/auth/logout", json={"refresh_token": tokens["refresh_token"]}).status_code == 200
    assert client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]}).status_code == 401


def test_password_reset(client, customer):
    token = client.post("/auth/forgot-password", json={"email": "guest@test.com"}).json()["reset_token"]
    r = client.post("/auth/reset-password", json={"token": token, "new_password": "brandnew123"})
    assert r.status_code == 200

    assert client.post("/auth/login", data={"username": "guest@test.com", "password": PASSWORD}).status_code == 401
    assert client.post("/auth/login", data={"username": "guest@test.com", "password": "brandnew123"}).status_code == 200


def test_forgot_password_unknown_email_gives_same_message(client):
    r = client.post("/auth/forgot-password", json={"email": "nobody@test.com"})
    assert r.status_code == 200
    assert r.json()["reset_token"] is None


def test_login_lockout_after_five_failures(client, customer):
    for _ in range(5):
        r = client.post("/auth/login", data={"username": "guest@test.com", "password": "wrong-pass"})
        assert r.status_code == 401
    # even the right password is refused now
    r = client.post("/auth/login", data={"username": "guest@test.com", "password": PASSWORD})
    assert r.status_code == 429


def test_customer_cannot_open_admin_routes(client, customer):
    assert client.get("/admin/users", headers=customer).status_code == 403


def test_seeded_admin_can_log_in(api):
    assert api.login(ADMIN_EMAIL, ADMIN_PASSWORD)
