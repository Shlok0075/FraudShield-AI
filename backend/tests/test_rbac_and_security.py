"""
Security-adjacent access-control tests (PART 15 SECURITY TESTING, Week 13 Day 6):
unauthorized request -> 401, invalid JWT -> 401, wrong-role request -> 403,
SQL-injection-style input safely rejected (ORM prevents it -- verified
explicitly here).
"""


def test_unauthorized_request_returns_401(client):
    resp = client.get("/api/v1/dashboard/kpis")
    assert resp.status_code == 401


def test_invalid_jwt_returns_401(client):
    resp = client.get("/api/v1/dashboard/kpis", headers={"Authorization": "Bearer garbage.token.value"})
    assert resp.status_code == 401


def test_wrong_role_returns_403_on_admin_only_route(client, user_token):
    resp = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {user_token}"})
    assert resp.status_code == 403


def test_wrong_role_returns_403_on_admin_analyst_route(client, user_token):
    resp = client.patch(
        "/api/v1/transactions/1/action",
        json={"action": "mark_reviewed"},
        headers={"Authorization": f"Bearer {user_token}"},
    )
    assert resp.status_code == 403


def test_admin_can_access_admin_only_route(client, admin_token):
    resp = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 200


def test_sql_injection_style_input_is_safely_rejected(client, admin_token):
    """The amount field is a Pydantic float; a SQL-injection-style string
    is rejected by validation BEFORE it ever reaches the ORM/SQL layer."""
    resp = client.post(
        "/api/v1/transactions/predict",
        json={
            "user_id": 1,
            "amount": "1; DROP TABLE users;--",
            "device_id": "dev-1",
        },
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422  # VALIDATION_ERROR, never reaches SQL


def test_negative_amount_rejected(client, admin_token):
    resp = client.post(
        "/api/v1/transactions/predict",
        json={"user_id": 1, "amount": -50, "device_id": "dev-1"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422


def test_error_response_format_is_consistent(client):
    resp = client.get("/api/v1/dashboard/kpis")
    body = resp.json()
    assert "error" in body
    assert "code" in body["error"]
    assert "message" in body["error"]


# ---- Public registration role-escalation protection ----

def test_public_register_with_admin_role_creates_user(client):
    """Client-supplied admin role must be ignored during public registration."""
    resp = client.post("/api/v1/auth/register", json={
        "email": "sec_attacker@fraudshield.ai", "password": "StrongPass123!", "role": "admin",
    })
    assert resp.status_code == 201
    assert resp.json()["role"] == "user"


def test_public_register_with_analyst_role_creates_user(client):
    """Client-supplied analyst role must be ignored during public registration."""
    resp = client.post("/api/v1/auth/register", json={
        "email": "sec_attacker2@fraudshield.ai", "password": "StrongPass123!", "role": "analyst",
    })
    assert resp.status_code == 201
    assert resp.json()["role"] == "user"


def test_public_register_defaults_to_user_role(client):
    """Public registration with no role field must create a user."""
    resp = client.post("/api/v1/auth/register", json={
        "email": "sec_normal@fraudshield.ai", "password": "StrongPass123!",
    })
    assert resp.status_code == 201
    assert resp.json()["role"] == "user"


# ---- Admin-only user creation protection ----

def test_unauthenticated_cannot_create_user(client):
    """POST /api/v1/users without a token must return 401."""
    resp = client.post("/api/v1/users", json={
        "email": "sec_new@fraudshield.ai", "password": "StrongPass123!", "role": "user",
    })
    assert resp.status_code == 401


def test_analyst_cannot_create_admin_user(client, user_token):
    """An analyst must not be able to create admin accounts via /api/v1/users."""
    resp = client.post("/api/v1/users", json={
        "email": "sec_newadmin@fraudshield.ai", "password": "StrongPass123!", "role": "admin",
    }, headers={"Authorization": f"Bearer {user_token}"})
    assert resp.status_code == 403


def test_admin_can_create_admin_user(client, admin_token):
    """An admin can create another admin account via /api/v1/users."""
    resp = client.post("/api/v1/users", json={
        "email": "sec_created_admin@fraudshield.ai", "password": "StrongPass123!", "role": "admin",
    }, headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    assert resp.json()["role"] == "admin"


def test_admin_can_create_analyst_user(client, admin_token):
    """An admin can create an analyst account via /api/v1/users."""
    resp = client.post("/api/v1/users", json={
        "email": "sec_created_analyst@fraudshield.ai", "password": "StrongPass123!", "role": "analyst",
    }, headers={"Authorization": f"Bearer {admin_token}"})
    assert resp.status_code == 201
    assert resp.json()["role"] == "analyst"
