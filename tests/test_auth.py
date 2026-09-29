def signup(client, *, name="Alice", email="alice@demo.io", password="password123", role="USER"):
    return client.post(
        "/api/auth/signup",
        json={"name": name, "email": email, "password": password, "role": role},
    )


def login(client, *, email="alice@demo.io", password="password123"):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def test_signup_success(client):
    res = signup(client)
    assert res.status_code == 201
    body = res.json()
    assert body["email"] == "alice@demo.io"
    assert body["role"] == "USER"
    # Safe response never leaks credentials.
    assert "password" not in body
    assert "password_hash" not in body


def test_signup_duplicate_email(client):
    signup(client)
    res = signup(client)
    assert res.status_code == 409


def test_signup_invalid_role(client):
    res = signup(client, role="ADMIN")
    assert res.status_code == 422


def test_login_success(client):
    signup(client)
    res = login(client)
    assert res.status_code == 200
    body = res.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "alice@demo.io"


def test_login_invalid_password(client):
    signup(client)
    res = login(client, password="wrong-password")
    assert res.status_code == 401
    assert res.json()["detail"] == "Invalid email or password"


def test_me_authenticated(client):
    signup(client)
    token = login(client).json()["access_token"]
    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    body = res.json()
    assert body["email"] == "alice@demo.io"
    assert body["role"] == "USER"


def test_me_unauthenticated(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401


def test_me_invalid_jwt(client):
    res = client.get(
        "/api/auth/me", headers={"Authorization": "Bearer not-a-real-token"}
    )
    assert res.status_code == 401


def test_role_based_access(client):
    # A USER cannot access the reviewer-only listing.
    signup(client, email="user@demo.io", role="USER")
    user_token = login(client, email="user@demo.io").json()["access_token"]
    res = client.get(
        "/api/requests", headers={"Authorization": f"Bearer {user_token}"}
    )
    assert res.status_code == 403

    # A REVIEWER can.
    signup(client, name="Rev", email="rev@demo.io", role="REVIEWER")
    rev_token = login(client, email="rev@demo.io").json()["access_token"]
    res = client.get(
        "/api/requests", headers={"Authorization": f"Bearer {rev_token}"}
    )
    assert res.status_code == 200
