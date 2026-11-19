import pytest
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


# ---- performance / portability regressions ---------------------------------------------------
def test_trends_bucket_sql_is_valid_for_both_databases():
    """strftime only exists in SQLite; Postgres needs to_char (the trend chart was broken there)."""
    from app.routes.dashboard import _bucket_sql
    assert _bucket_sql("sqlite", "t.created_at", "day").startswith("strftime(")
    pg = _bucket_sql("postgresql", "t.created_at", "hour")
    assert "to_char(" in pg and "strftime" not in pg and "HH24" in pg
    assert "HH24" not in _bucket_sql("postgresql", "t.created_at", "day")


def test_counterparty_count_is_cached_and_never_rescans_corpus(db_session):
    """Without paysim_merchant_counts the corpus count must be computed once, not per transaction."""
    from sqlalchemy import event
    from app.models.transaction import Transaction
    from app.services import feature_engineering as fe
    db_session.add_all([Transaction(id=-i, user_id=i, amount=10, currency="INR", status="pending")
                        for i in range(1, 6)])
    db_session.add(Transaction(id=0, user_id=1, amount=10, currency="INR", status="pending"))
    db_session.commit()
    fe._CORPUS_CP_COUNT.clear(); fe._HAS_MERCHANT_ROLLUP.clear()

    seen = []
    event.listen(db_session.get_bind(), "before_cursor_execute",
                 lambda c, cur, stmt, *a: seen.append(stmt))
    first = fe._merchant_prior_count(db_session, None, fe.UNKNOWN_MERCHANT_KEY)
    n_first = len([s for s in seen if "id <" in s.lower()])
    second = fe._merchant_prior_count(db_session, None, fe.UNKNOWN_MERCHANT_KEY)
    n_total = len([s for s in seen if "id <" in s.lower()])
    assert first == second == 6                       # 5 corpus + 1 live row
    assert n_first == 1 and n_total == 1              # corpus scan happened exactly once


@pytest.mark.anyio
async def test_ingest_does_not_block_the_event_loop(db_session):
    """The event loop must keep running while a transaction is being scored."""
    import asyncio
    from app.services.prediction_pipeline import ingest_transaction
    ticks = 0

    async def ticker():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.001)
            ticks += 1

    t = asyncio.create_task(ticker())
    payload = {"user_id": 7, "amount": 500.0, "device_id": "dev-x", "payment_method": "card"}
    await ingest_transaction(db_session, payload, emit=False)
    t.cancel()
    assert ticks > 0


@pytest.fixture
def anyio_backend():
    return "asyncio"
