"""Unit tests for auth: register/login/me, token creation/expiry/invalid
token rejection, password hashing (PART 15 UNIT TESTING)."""
import time

from app.auth.security import create_access_token, decode_access_token, hash_password, verify_password


def test_password_hash_and_verify():
    hashed = hash_password("StrongPass123!")
    assert hashed != "StrongPass123!"
    assert verify_password("StrongPass123!", hashed)
    assert not verify_password("WrongPassword", hashed)


def test_create_and_decode_access_token():
    token = create_access_token(subject="1", role="admin")
    payload = decode_access_token(token)
    assert payload["sub"] == "1"
    assert payload["role"] == "admin"


def test_register_and_login_flow(client):
    resp = client.post("/api/v1/auth/register", json={
        "email": "newuser@fraudshield.ai", "password": "StrongPass123!",
    })
    assert resp.status_code == 201
    # Public registration always creates a normal user role
    assert resp.json()["role"] == "user"

    login_resp = client.post("/api/v1/auth/login", json={
        "email": "newuser@fraudshield.ai", "password": "StrongPass123!",
    })
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()


def test_public_register_with_admin_role_creates_user(client):
    """Client-supplied role must be ignored during public registration."""
    resp = client.post("/api/v1/auth/register", json={
        "email": "attacker@fraudshield.ai", "password": "StrongPass123!", "role": "admin",
    })
    assert resp.status_code == 201
    assert resp.json()["role"] == "user"


def test_public_register_with_analyst_role_creates_user(client):
    """Client-supplied analyst role must be ignored during public registration."""
    resp = client.post("/api/v1/auth/register", json={
        "email": "attacker2@fraudshield.ai", "password": "StrongPass123!", "role": "analyst",
    })
    assert resp.status_code == 201
    assert resp.json()["role"] == "user"


def test_login_rejects_wrong_password(client):
    client.post("/api/v1/auth/register", json={
        "email": "x@fraudshield.ai", "password": "StrongPass123!", "role": "user",
    })
    resp = client.post("/api/v1/auth/login", json={"email": "x@fraudshield.ai", "password": "WrongOne!"})
    assert resp.status_code == 401


def test_register_rejects_duplicate_email(client):
    payload = {"email": "dup@fraudshield.ai", "password": "StrongPass123!"}
    first = client.post("/api/v1/auth/register", json=payload)
    second = client.post("/api/v1/auth/register", json=payload)
    assert first.status_code == 201
    assert second.status_code == 400


def test_me_requires_valid_token(client, admin_token):
    ok = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {admin_token}"})
    assert ok.status_code == 200
    assert ok.json()["role"] == "admin"

    bad = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert bad.status_code == 401


def test_no_token_is_unauthorized(client):
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
