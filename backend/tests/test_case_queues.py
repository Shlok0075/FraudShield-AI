"""Cases page queues: escalated cases are sorted into work queues instead of one mixed list."""
from datetime import datetime, timedelta, timezone
from itertools import product

import pytest

from app.models.case import FraudCase
from app.models.fraud_alert import FraudAlert
from app.models.transaction import Transaction
from app.routes.cases import QUEUES, queue_of

H = lambda token: {"Authorization": f"Bearer {token}"}  # noqa: E731


def add_case(db, decision=None, status="open", priority="medium", age_min=0, amount=100.0):
    txn = Transaction(user_id=1, amount=amount, currency="INR", status="flagged")
    db.add(txn); db.commit(); db.refresh(txn)
    when = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=age_min)
    alert = FraudAlert(transaction_id=txn.id, severity="HIGH", status="escalated", created_at=when)
    db.add(alert); db.commit(); db.refresh(alert)
    case = FraudCase(alert_id=alert.id, status=status, priority=priority, decision=decision,
                     created_at=when, updated_at=when)
    db.add(case); db.commit(); db.refresh(case)
    return case


@pytest.mark.parametrize("decision,status,expected", [
    (None, "open", "needs_review"),
    ("needs_review", "open", "needs_review"),
    ("unresolved", "investigating", "needs_review"),
    ("REVIEW", "open", "needs_review"),                  # older code stored the engine verdict verbatim
    ("auto_blocked", "open", "auto_blocked"),
    ("AUTO_BLOCK", "open", "auto_blocked"),
    ("AUTO_BLOCK", "closed", "closed"),                  # older code closed these as "fraud"
    ("auto_cleared", "closed", "auto_cleared"),
    ("AUTO_CLEAR", "closed", "auto_cleared"),
    ("confirmed_fraud", "closed", "closed"),
    ("false_positive", "closed", "closed"),
    ("confirmed_fraud", "open", "closed"),               # a human's decision always wins
    (None, "closed", "closed"),
])
def test_queue_rules(decision, status, expected):
    assert queue_of(decision, status) == expected


def test_database_filter_and_python_rule_always_agree(client, db_session, admin_token):
    decisions = [None, "needs_review", "unresolved", "REVIEW", "auto_blocked", "AUTO_BLOCK", "auto_cleared",
                 "AUTO_CLEAR", "confirmed_fraud", "false_positive"]
    cases = [add_case(db_session, d, s) for d, s in product(decisions, ["open", "investigating", "closed"])]
    for q in QUEUES:
        got = {c["id"] for c in client.get(f"/api/v1/cases?queue={q}&limit=500", headers=H(admin_token)).json()}
        want = {c.id for c in cases if queue_of(c.decision, c.status) == q}
        assert got == want, q
    counts = client.get("/api/v1/cases/queues", headers=H(admin_token)).json()
    assert sum(v["count"] for v in counts["queues"].values()) == len(cases)   # exactly one queue each


def test_queues_endpoint_is_not_shadowed_by_the_case_id_route(client, admin_token):
    r = client.get("/api/v1/cases/queues", headers=H(admin_token))
    assert r.status_code == 200 and set(r.json()["queues"]) == set(QUEUES)


def test_counts_include_priority_mix_and_needs_attention(client, db_session, admin_token):
    add_case(db_session, "needs_review", priority="critical")
    add_case(db_session, "needs_review", priority="low")
    add_case(db_session, "auto_blocked", priority="critical")
    add_case(db_session, "auto_cleared", "closed", priority="low")
    body = client.get("/api/v1/cases/queues", headers=H(admin_token)).json()
    assert body["queues"]["needs_review"] == {"count": 2, "by_priority": {"critical": 1, "high": 0, "medium": 0, "low": 1}}
    assert body["queues"]["auto_blocked"]["count"] == 1 and body["queues"]["auto_cleared"]["count"] == 1
    assert body["needs_attention"] == 3                  # auto-cleared cases do not need anyone


def test_work_queues_are_ordered_most_severe_then_oldest(client, db_session, admin_token):
    a = add_case(db_session, "needs_review", priority="low", age_min=500)
    b = add_case(db_session, "needs_review", priority="critical", age_min=5)
    c = add_case(db_session, "needs_review", priority="high", age_min=50)
    d = add_case(db_session, "needs_review", priority="critical", age_min=90)   # waited longer than b
    ids = [x["id"] for x in client.get("/api/v1/cases?queue=needs_review", headers=H(admin_token)).json()]
    assert ids == [d.id, b.id, c.id, a.id]


def test_priority_filter_and_validation(client, db_session, admin_token):
    add_case(db_session, "needs_review", priority="critical")
    add_case(db_session, "needs_review", priority="low")
    rows = client.get("/api/v1/cases?queue=needs_review&priority=critical", headers=H(admin_token)).json()
    assert len(rows) == 1 and rows[0]["priority"] == "critical"
    assert client.get("/api/v1/cases?queue=nonsense", headers=H(admin_token)).status_code == 422
    assert client.get("/api/v1/cases?priority=urgent", headers=H(admin_token)).status_code == 422


def test_rows_carry_triage_context(client, db_session, admin_token):
    c = add_case(db_session, "needs_review", amount=12345.5)
    row = client.get("/api/v1/cases?queue=needs_review", headers=H(admin_token)).json()[0]
    assert row["queue"] == "needs_review" and row["severity"] == "HIGH"
    assert row["amount"] == 12345.5 and row["currency"] == "INR" and row["transaction_id"] is not None   # live ids start at 0
    assert client.get(f"/api/v1/cases/{c.id}", headers=H(admin_token)).json()["amount"] == 12345.5


def test_an_analyst_decision_moves_the_case_between_queues(client, db_session, admin_token):
    c = add_case(db_session, "auto_blocked")
    assert client.get("/api/v1/cases/queues", headers=H(admin_token)).json()["queues"]["auto_blocked"]["count"] == 1
    r = client.patch(f"/api/v1/cases/{c.id}", json={"decision": "confirmed_fraud", "status": "closed"},
                     headers=H(admin_token))
    assert r.status_code == 200 and r.json()["queue"] == "closed"
    q = client.get("/api/v1/cases/queues", headers=H(admin_token)).json()["queues"]
    assert q["auto_blocked"]["count"] == 0 and q["closed"]["count"] == 1


def test_queue_pagination_does_not_overlap(client, db_session, admin_token):
    for i in range(7):
        add_case(db_session, "needs_review", priority="high", age_min=i)
    first = client.get("/api/v1/cases?queue=needs_review&limit=4", headers=H(admin_token)).json()
    rest = client.get("/api/v1/cases?queue=needs_review&limit=4&offset=4", headers=H(admin_token)).json()
    ids = [c["id"] for c in first + rest]
    assert len(first) == 4 and len(rest) == 3 and len(set(ids)) == 7


REPORT = """FRAUDSHIELD AI — AUTOMATED INVESTIGATION REPORT
==================================================
Investigation Confidence: 91%
Auto-Decision: AUTO_BLOCK
Risk Level: CRITICAL
Investigated At: 2026-10-30T07:50:52+00:00

EVIDENCE SIGNALS:
------------------------------
  • Supervised ML (XGBoost): 96% (weight 40%)
  • Behavioral Deviation: 55% (weight 20%)

AUTOMATED CHECKS:
------------------------------
  [FRAUD] velocity: 6 transactions in 1 minute (confidence 80%)

REASONING:
------------------------------
  High-confidence fraud indicators detected across multiple signals.

RECOMMENDED ACTION:
  Keep the transaction blocked and have an analyst confirm or overturn it.
"""


def test_report_is_structured_and_not_duplicated_as_a_note(client, db_session, admin_token):
    from app.models.case import CaseNote
    case = add_case(db_session, "auto_blocked")
    db_session.add(CaseNote(case_id=case.id, author_id=1, note=REPORT))
    db_session.add(CaseNote(case_id=case.id, author_id=1, note="called the customer"))
    db_session.commit()
    body = client.get(f"/api/v1/cases/{case.id}", headers=H(admin_token)).json()
    inv = body["investigation"]
    assert inv["confidence"] == 91 and inv["risk_level"] == "CRITICAL"
    assert inv["signals"][0] == {"name": "Supervised ML (XGBoost)", "score": 96}
    assert inv["checks"] == ["velocity: 6 transactions in 1 minute (confidence 80%)"]
    assert "confirm or overturn" in inv["recommendation"]
    assert [n["note"] for n in body["notes"]] == ["called the customer"]


def test_case_without_report_has_no_investigation(client, db_session, admin_token):
    case = add_case(db_session)
    assert client.get(f"/api/v1/cases/{case.id}", headers=H(admin_token)).json()["investigation"] is None


def test_deciding_a_case_closes_and_assigns_it_automatically(client, db_session, admin_token):
    case = add_case(db_session, "auto_blocked")
    r = client.patch(f"/api/v1/cases/{case.id}", json={"decision": "confirmed_fraud"}, headers=H(admin_token))
    body = r.json()
    assert r.status_code == 200
    assert body["status"] == "closed" and body["queue"] == "closed" and body["assigned_to"] is not None
