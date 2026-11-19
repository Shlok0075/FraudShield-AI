"""Auto-investigation: what gets closed without a human, and the safety rails around it.

Foreign keys are ENFORCED here (SQLite ignores them by default, which hid a bug where alerts were
resolved by user id -1 and every auto-resolution failed on Postgres).
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ml" / "src"))

from app.auth.security import hash_password
from app.config.settings import settings
from app.models.audit_log import AuditLog
from app.models.case import CaseNote, FraudCase
from app.models.fraud_alert import FraudAlert
from app.models.fraud_prediction import FraudPrediction
from app.models.transaction import Transaction
from app.models.user import User
from app.services.auto_investigator import escalate_stale_cases, sweep_once
from app.services.investigation_service import SYSTEM_EMAIL, get_system_user, run_investigation
from fraudpipe.investigation_engine import InvestigationEngine


@pytest.fixture()
def fk_db(db_session):
    """The test database with foreign keys switched on."""
    db_session.commit()
    db_session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    db_session.commit()
    return db_session


def make_alert(db, ml=0.05, anomaly=0.0, behavior=0.0, rules=0.0, graph=0.0, status="open",
               age_s=60, with_case=True):
    txn = Transaction(user_id=1, amount=500, currency="INR", status="flagged")
    db.add(txn); db.commit(); db.refresh(txn)
    db.add(FraudPrediction(transaction_id=txn.id, probability=ml, risk_score=int(ml * 100),
                           risk_level="HIGH", model_version="t", anomaly_score=anomaly,
                           behavior_score=behavior, rule_score=rules, graph_score=graph,
                           triggered_rules=[]))
    created = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=age_s)
    alert = FraudAlert(transaction_id=txn.id, severity="HIGH", status=status, created_at=created)
    db.add(alert); db.commit(); db.refresh(alert)
    case = None
    if with_case:
        case = FraudCase(alert_id=alert.id, status="open", priority="medium")
        db.add(case); db.commit(); db.refresh(case)
    return txn, alert, case


# ----------------------------------------------------------------------------- engine decisions
@pytest.mark.parametrize("signals,expected", [
    (dict(ml_prob=0.99, anomaly_score=0, behavior_score=0, rule_score=0, graph_score=0), "REVIEW"),
    (dict(ml_prob=0.99, anomaly_score=0.8, behavior_score=0, rule_score=0, graph_score=0), "AUTO_BLOCK"),
    (dict(ml_prob=1, anomaly_score=1, behavior_score=1, rule_score=1, graph_score=1), "AUTO_BLOCK"),
    (dict(ml_prob=0.05, anomaly_score=0.05, behavior_score=0.05, rule_score=0, graph_score=0), "AUTO_CLEAR"),
    (dict(ml_prob=0.35, anomaly_score=0, behavior_score=0, rule_score=0, graph_score=0), "REVIEW"),
    (dict(ml_prob=None, anomaly_score=None, behavior_score=None, rule_score=None, graph_score=None), "REVIEW"),
])
def test_engine_decisions(signals, expected):
    r = InvestigationEngine().investigate(**signals, triggered_rules=[], features={}, graph_features={})
    assert r.decision == expected


def test_a_model_flagged_transaction_is_never_auto_cleared():
    """Regression: ML 0.99 with nothing else firing used to average to 15 and be cleared."""
    r = InvestigationEngine().investigate(ml_prob=0.99, anomaly_score=0, behavior_score=0, rule_score=0,
                                          graph_score=0, triggered_rules=[], features={}, graph_features={})
    assert r.decision != "AUTO_CLEAR" and r.confidence >= 90


def test_a_triggered_rule_prevents_auto_clear():
    r = InvestigationEngine().investigate(ml_prob=0.05, anomaly_score=0, behavior_score=0, rule_score=0,
                                          graph_score=0, triggered_rules=[{"name": "r1"}], features={},
                                          graph_features={})
    assert r.decision == "REVIEW"


# ----------------------------------------------------------------------------- persistence policy
def test_auto_clear_closes_case_and_uses_a_real_system_user(fk_db):
    fk_db.add(User(email="first@real.person", password_hash="x", role="admin"))   # user id 1 is a human
    fk_db.commit()
    txn, alert, case = make_alert(fk_db, ml=0.05)
    out = run_investigation(fk_db, alert.id, emit=False)
    fk_db.refresh(alert); fk_db.refresh(case); fk_db.refresh(txn)

    assert out["applied"] == "AUTO_CLEAR"
    assert (case.status, case.decision) == ("closed", "auto_cleared") and case.closed_at
    assert (alert.status, txn.status) == ("false_positive", "allowed")
    system = fk_db.execute(select(User).where(User.email == SYSTEM_EMAIL)).scalar_one()
    assert alert.resolved_by == system.id                       # a real row, so the FK holds
    note = fk_db.execute(select(CaseNote).where(CaseNote.case_id == case.id)).scalar_one()
    assert note.author_id == system.id                          # not user #1, a real person
    assert fk_db.execute(select(AuditLog).where(AuditLog.action == "investigation.auto_clear")).scalar_one()


def test_auto_block_blocks_but_leaves_fraud_confirmation_to_a_human(fk_db):
    txn, alert, case = make_alert(fk_db, ml=0.99, anomaly=0.8)
    out = run_investigation(fk_db, alert.id, emit=False)
    fk_db.refresh(alert); fk_db.refresh(case); fk_db.refresh(txn)
    assert out["applied"] == "AUTO_BLOCK"
    assert txn.status == "blocked" and alert.status == "escalated"
    assert (case.status, case.decision, case.priority) == ("open", "auto_blocked", "critical")
    assert case.closed_at is None


def test_ambiguous_alert_is_escalated_to_an_analyst(fk_db):
    txn, alert, case = make_alert(fk_db, ml=0.5)
    run_investigation(fk_db, alert.id, emit=False)
    fk_db.refresh(alert); fk_db.refresh(case)
    assert alert.status == "escalated" and (case.status, case.decision) == ("open", "needs_review")


def test_a_humans_decision_is_never_overwritten(fk_db):
    _, alert, case = make_alert(fk_db, ml=0.05)
    case.status, case.decision = "closed", "confirmed_fraud"
    fk_db.commit()
    out = run_investigation(fk_db, alert.id, emit=False)
    fk_db.refresh(case)
    assert "skipped" in out and case.decision == "confirmed_fraud" and case.status == "closed"


@pytest.mark.parametrize("flag", ["AUTO_RESOLVE_SHADOW", "AUTO_RESOLVE_ENABLED"])
def test_shadow_and_disabled_modes_change_nothing_automatically(fk_db, monkeypatch, flag):
    monkeypatch.setattr(settings, flag, flag == "AUTO_RESOLVE_SHADOW")
    txn, alert, case = make_alert(fk_db, ml=0.05)                 # would be AUTO_CLEAR
    out = run_investigation(fk_db, alert.id, emit=False)
    fk_db.refresh(alert); fk_db.refresh(case); fk_db.refresh(txn)
    assert out["decision"] == "AUTO_CLEAR" and out["applied"] == "REVIEW" and out["acting"] is False
    assert (case.status, case.decision) == ("open", "needs_review") and alert.status == "escalated"
    assert txn.status == "flagged"
    note = fk_db.execute(select(CaseNote).where(CaseNote.case_id == case.id)).scalar_one()
    assert "AUTO_CLEAR" in note.note and note.note.startswith("[")


def test_old_system_account_with_a_hardcoded_password_is_locked_down(db_session):
    db_session.add(User(email=SYSTEM_EMAIL, password_hash=hash_password("system-auto-generated"), role="admin"))
    db_session.commit()
    before = db_session.execute(select(User.password_hash).where(User.email == SYSTEM_EMAIL)).scalar_one()
    user = get_system_user(db_session)
    assert user.role == "user" and user.password_hash != before


# ----------------------------------------------------------------------------- sweeper
def test_sweeper_investigates_open_alerts_once_and_isolates_failures(fk_db):
    _, a_clear, _ = make_alert(fk_db, ml=0.02)
    _, a_block, _ = make_alert(fk_db, ml=0.99, anomaly=0.9)
    _, a_review, _ = make_alert(fk_db, ml=0.5)
    _, a_young, _ = make_alert(fk_db, ml=0.02, age_s=0)            # too new: inline path may still own it
    broken = FraudAlert(transaction_id=99999, severity="HIGH", status="open",
                        created_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5))
    fk_db.execute(__import__("sqlalchemy").text("PRAGMA foreign_keys=OFF")); fk_db.add(broken); fk_db.commit()
    fk_db.execute(__import__("sqlalchemy").text("PRAGMA foreign_keys=ON")); fk_db.commit()

    res = sweep_once(fk_db, min_age_s=30)
    assert res["errors"] == 1                                       # the bad alert did not stop the rest
    assert res["applied"] == {"AUTO_CLEAR": 1, "AUTO_BLOCK": 1, "REVIEW": 1}
    for a in (a_clear, a_block, a_review, a_young):
        fk_db.refresh(a)
    assert a_clear.status == "false_positive" and a_block.status == "escalated" and a_review.status == "escalated"
    assert a_young.status == "open"

    again = sweep_once(fk_db, min_age_s=30)                         # idempotent
    assert again["examined"] == 1 and again["applied"] == {"AUTO_CLEAR": 0, "AUTO_BLOCK": 0, "REVIEW": 0}


def test_unattended_cases_are_escalated_once(fk_db):
    _, _, stale = make_alert(fk_db, ml=0.5, status="escalated")
    _, _, fresh = make_alert(fk_db, ml=0.5, status="escalated")
    stale.updated_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(hours=10)
    fk_db.commit()
    assert escalate_stale_cases(fk_db) == 1
    fk_db.refresh(stale); fk_db.refresh(fresh)
    assert stale.priority == "high" and fresh.priority == "medium"
    assert escalate_stale_cases(fk_db) == 0


def test_stats_endpoint_reports_automation(client, fk_db, admin_token):
    _, alert, _ = make_alert(fk_db, ml=0.02)
    run_investigation(fk_db, alert.id, emit=False)
    r = client.get("/api/v1/investigation/stats", headers={"Authorization": f"Bearer {admin_token}"})
    assert r.status_code == 200
    body = r.json()
    assert body["auto_handled"] == 1 and body["cases_by_decision"]["auto_cleared"] == 1
    assert body["policy"] == {"auto_resolve_enabled": True, "shadow_mode": False}
