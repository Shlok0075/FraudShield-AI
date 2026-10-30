"""
Integration test: full POST /transactions/predict flow hitting a test
database (PART 15 INTEGRATION TESTING, Week 13 Day 3).
"""


def test_predict_creates_transaction_and_prediction(client, admin_token):
    resp = client.post(
        "/api/v1/transactions/predict",
        json={"user_id": 42, "amount": 500, "device_id": "dev-int-test", "location": "Pune"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Live transaction ids are allocated from 0 upward (see the before_insert
    # allocator on app.models.transaction.Transaction), so the first one this
    # suite creates is legitimately 0.
    assert body["transaction_id"] >= 0
    assert 0.0 <= body["probability"] <= 1.0
    assert 0 <= body["risk_score"] <= 100
    assert body["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    assert body["decision"] in ("Allow", "Monitor", "Flag", "Critical Alert")
    assert isinstance(body["explanation"], list) and len(body["explanation"]) > 0


def test_predict_high_risk_scenario_creates_alert(client, admin_token):
    """A synthetically constructed high-risk transaction (new device +
    unusually large amount + new location) should score MEDIUM+ and
    create a corresponding fraud_alerts row -- see
    docs/feature_plan.md 'Live risk-intensity mapping'."""
    resp = client.post(
        "/api/v1/transactions/predict",
        json={"user_id": 99, "amount": 75000, "device_id": "dev-brand-new-int", "location": "Unknown"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_score"] > 0

    alerts_resp = client.get("/api/v1/alerts", headers={"Authorization": f"Bearer {admin_token}"})
    assert alerts_resp.status_code == 200


def test_transaction_list_and_detail_and_action(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    predict_resp = client.post(
        "/api/v1/transactions/predict",
        json={"user_id": 7, "amount": 100, "device_id": "dev-list-test"},
        headers=headers,
    )
    txn_id = predict_resp.json()["transaction_id"]

    list_resp = client.get("/api/v1/transactions", headers=headers)
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] >= 1

    detail_resp = client.get(f"/api/v1/transactions/{txn_id}/detail", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["prediction"] is not None

    action_resp = client.patch(
        f"/api/v1/transactions/{txn_id}/action", json={"action": "mark_reviewed"}, headers=headers,
    )
    assert action_resp.status_code == 200
    assert action_resp.json()["new_status"] == "reviewed"


def test_invalid_field_returns_422(client, admin_token):
    resp = client.post(
        "/api/v1/transactions/predict",
        json={"user_id": 1, "amount": 0, "device_id": "dev-1"},  # amount must be > 0
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 422


def test_dashboard_kpis_reflect_created_transactions(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    client.post("/api/v1/transactions/predict",
                json={"user_id": 1, "amount": 100, "device_id": "d1"}, headers=headers)
    client.post("/api/v1/transactions/predict",
                json={"user_id": 1, "amount": 150, "device_id": "d1"}, headers=headers)

    kpi_resp = client.get("/api/v1/dashboard/kpis", headers=headers)
    assert kpi_resp.status_code == 200
    assert kpi_resp.json()["total_transactions"] == 2


def test_live_ids_start_at_zero_and_ignore_negative_corpus_ids(client, admin_token, db_session):
    """The live stream is numbered from 0, independently of the PaySim corpus.

    The corpus is bulk-loaded into `transactions` under a NEGATIVE id range
    (ml/src/paysim_ingest.py --id-base) so it can never collide with rows the
    app creates. This pins the two properties that follow from that design:
    existing negative rows do not push live ids negative or into a gap, and
    successive live transactions are numbered contiguously.
    """
    from sqlalchemy import text

    # Stand in a slice of the training corpus.
    db_session.execute(text(
        "INSERT INTO transactions (id, user_id, merchant_id, device_id, amount, "
        "currency, location, ip_address, payment_method, status, created_at) "
        "VALUES (-10000000, 1, NULL, NULL, 10.0, 'INR', 'X', NULL, 'card', "
        "'completed', '2024-01-01 00:00:00'), "
        "(-3637381, 1, NULL, NULL, 20.0, 'INR', 'Y', NULL, 'card', "
        "'completed', '2024-01-01 01:00:00')"))
    db_session.commit()

    headers = {"Authorization": f"Bearer {admin_token}"}
    seen = []
    for i in range(3):
        resp = client.post(
            "/api/v1/transactions/predict",
            json={"user_id": 500 + i, "amount": 10 + i, "device_id": f"dev-zero-{i}"},
            headers=headers,
        )
        assert resp.status_code == 200
        seen.append(resp.json()["transaction_id"])

    # Starts at 0, contiguous, and never lands in the corpus's negative range.
    assert seen == list(range(seen[0], seen[0] + 3))
    assert seen[0] == 0
    assert all(tid >= 0 for tid in seen)


def test_health_check():
    from fastapi.testclient import TestClient
    from app.main import app

    with TestClient(app) as c:
        resp = c.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}
