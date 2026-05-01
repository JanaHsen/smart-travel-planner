"""
Auth endpoint integration tests.

Uses the `client` fixture from conftest which wires the FastAPI app to the
test Postgres database via the overridden get_session dependency.  Each test
uses a unique email address so tests are order-independent.
"""
import uuid


# ---------------------------------------------------------------------------
# POST /auth/register
# ---------------------------------------------------------------------------


async def test_register_creates_user(client):
    email = f"user_{uuid.uuid4().hex[:10]}@example.com"
    resp = await client.post("/auth/register", json={"email": email, "password": "securepass"})

    assert resp.status_code == 201
    body = resp.json()
    assert body["email"] == email
    assert "id" in body
    assert "hashed_password" not in body  # never leaked


async def test_register_rejects_duplicate_email(client):
    email = f"dup_{uuid.uuid4().hex[:10]}@example.com"
    payload = {"email": email, "password": "securepass"}

    first = await client.post("/auth/register", json=payload)
    assert first.status_code == 201

    second = await client.post("/auth/register", json=payload)
    assert second.status_code == 409
    assert "already registered" in second.json()["detail"].lower()


async def test_register_rejects_invalid_email(client):
    resp = await client.post("/auth/register", json={"email": "not-an-email", "password": "securepass"})
    assert resp.status_code == 422


async def test_register_rejects_short_password(client):
    email = f"pw_{uuid.uuid4().hex[:10]}@example.com"
    resp = await client.post("/auth/register", json={"email": email, "password": "short"})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


async def test_login_returns_token(client):
    email = f"login_{uuid.uuid4().hex[:10]}@example.com"
    password = "mypassword"

    reg = await client.post("/auth/register", json={"email": email, "password": password})
    assert reg.status_code == 201

    resp = await client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert len(body["access_token"]) > 20


async def test_login_rejects_wrong_password(client):
    email = f"wrong_{uuid.uuid4().hex[:10]}@example.com"

    await client.post("/auth/register", json={"email": email, "password": "correctpass"})

    resp = await client.post("/auth/login", json={"email": email, "password": "wrongpass"})
    assert resp.status_code == 401


async def test_login_rejects_unknown_email(client):
    resp = await client.post(
        "/auth/login",
        json={"email": "nobody@nowhere.com", "password": "whatever"},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Protected routes — token required
# ---------------------------------------------------------------------------


async def test_protected_route_rejects_no_token(client):
    resp = await client.get("/trips/history")
    assert resp.status_code == 401


async def test_protected_route_rejects_malformed_token(client):
    resp = await client.get("/trips/history", headers={"Authorization": "Bearer not.a.real.token"})
    assert resp.status_code == 401
