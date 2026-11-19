from app.models.fraud_prediction import FraudPrediction
from app.models.transaction import Transaction


def test_prediction_exposes_hybrid_signals(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    first = client.post("/api/v1/transactions/predict", json={
        "user_id": 777, "amount": 500, "device_id": "device-primary", "location": "Mumbai"
    }, headers=headers)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["hybrid_decision"] in ("ALLOW", "REVIEW", "BLOCK")
    assert 0 <= body["risk_score"] <= 100
    assert body["model_version"].startswith("live-")
    assert "anomaly_score" in body
    assert "behavior_score" in body
    assert "rule_score" in body
    assert isinstance(body["signal_contributions"], dict)


def test_new_device_is_evaluated_before_device_registration(client, admin_token):
    headers = {"Authorization": f"Bearer {admin_token}"}
    first = client.post("/api/v1/transactions/predict", json={
        "user_id": 778, "amount": 1000, "device_id": "device-a", "location": "Mumbai"
    }, headers=headers)
    assert first.status_code == 200
    second = client.post("/api/v1/transactions/predict", json={
        "user_id": 778, "amount": 1000, "device_id": "device-b", "location": "Delhi"
    }, headers=headers)
    assert second.status_code == 200
    assert second.json()["behavior_score"] >= 0


def test_txn_type_is_one_hot_encoded_for_the_model():
    """Regression: txn_type used to be silently dropped (all txn_type=* columns were 0)."""
    from app.ml.model_service import ModelService
    ModelService.load()
    cols = ModelService._feature_columns
    row = ModelService._matrix({"txn_type": "CASH_OUT"})[0]
    got = {c: v for c, v in zip(cols, row) if c.startswith("txn_type=")}
    assert got["txn_type=CASH_OUT"] == 1.0
    assert sum(got.values()) == 1.0
    assert sum(ModelService._matrix({"txn_type": "card"})[0][[i for i, c in enumerate(cols) if c.startswith("txn_type=")]]) == 0.0
