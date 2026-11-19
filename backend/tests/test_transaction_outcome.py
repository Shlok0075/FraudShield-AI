"""Transaction detail reports what the system did automatically instead of offering manual status buttons."""
from datetime import datetime, timezone

from app.models.case import FraudCase
from app.models.fraud_alert import FraudAlert
from app.models.transaction import Transaction

H = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731


def make(db, with_alert=True, decision=None, status="open"):
    txn = Transaction(user_id=1, amount=10.0, currency="INR", status="flagged")
    db.add(txn); db.commit(); db.refresh(txn)
    case = None
    if with_alert:
        alert = FraudAlert(transaction_id=txn.id, severity="HIGH", status="escalated")
        db.add(alert); db.commit(); db.refresh(alert)
        if decision is not None or status:
            case = FraudCase(alert_id=alert.id, status=status, decision=decision, priority="high")
            db.add(case); db.commit(); db.refresh(case)
    return txn, case


def outcome(client, token, txn):
    return client.get(f"/api/v1/transactions/{txn.id}/detail", headers=H(token)).json()["outcome"]


def test_no_alert_means_allowed_automatically(client, db_session, admin_token):
    txn, _ = make(db_session, with_alert=False)
    o = outcome(client, admin_token, txn)
    assert o["state"] == "allowed" and o["can_decide"] is False


def test_each_queue_maps_to_an_outcome(client, db_session, admin_token):
    for decision, status, state, can in [
        ("auto_cleared", "closed", "cleared", True),
        ("auto_blocked", "open", "blocked", True),
        ("needs_review", "open", "review", True),
        ("confirmed_fraud", "closed", "closed", False),
    ]:
        txn, case = make(db_session, decision=decision, status=status)
        o = outcome(client, admin_token, txn)
        assert (o["state"], o["can_decide"], o["case_id"]) == (state, can, case.id), decision
