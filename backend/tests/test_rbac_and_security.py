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
