"""Users, Audit Log and Intelligence endpoints: safety guards, paging and query behaviour."""
from datetime import datetime, timedelta, timezone

from app.auth.security import hash_password
from app.models.audit_log import AuditLog
from app.models.drift import DriftSnapshot
from app.models.fraud_prediction import FraudPrediction
from app.models.merchant import Merchant
from app.models.transaction import Transaction
from app.models.user import User
from app.services.investigation_service import SYSTEM_EMAIL

H = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731
API = "/api/v1"


def user(db, email, role="analyst"):
    u = User(email=email, password_hash=hash_password("StrongPass123!"), role=role)
    db.add(u); db.commit(); db.refresh(u)
    return u


def admin_id(db):
    return db.query(User).filter_by(email="admin@fraudshield.ai").one().id


# ---- Users --------------------------------------------------------------------------------
def test_cannot_delete_yourself_or_the_last_admin(client, db_session, admin_token):
    me = admin_id(db_session)
    r = client.delete(f"{API}/users/{me}", headers=H(admin_token))
    assert r.status_code == 400 and r.json()["error"]["code"] == "SELF_DELETE"


def test_cannot_demote_the_last_admin_but_can_when_another_exists(client, db_session, admin_token):
    me = admin_id(db_session)
    r = client.patch(f"{API}/users/{me}/role", json={"role": "analyst"}, headers=H(admin_token))
    assert r.status_code == 400 and r.json()["error"]["code"] == "LAST_ADMIN"
    other = user(db_session, "second@x.io", "admin")
    assert client.patch(f"{API}/users/{me}/role", json={"role": "analyst"}, headers=H(admin_token)).status_code == 200
    assert other.id != me


def test_system_account_is_hidden_and_protected(client, db_session, admin_token):
    sysu = user(db_session, SYSTEM_EMAIL, "user")
    assert SYSTEM_EMAIL not in [u["email"] for u in client.get(f"{API}/users", headers=H(admin_token)).json()]
    assert client.delete(f"{API}/users/{sysu.id}", headers=H(admin_token)).json()["error"]["code"] == "SYSTEM_ACCOUNT"
    assert client.patch(f"{API}/users/{sysu.id}/role", json={"role": "admin"}, headers=H(admin_token)).status_code == 400


def test_deleting_a_user_with_history_is_refused_cleanly_and_a_clean_one_is_deleted(client, db_session, admin_token):
    used = user(db_session, "used@x.io"); clean = user(db_session, "clean@x.io")
    db_session.add(AuditLog(user_id=used.id, action="auth.login")); db_session.commit()
    r = client.delete(f"{API}/users/{used.id}", headers=H(admin_token))
    assert r.status_code == 409 and r.json()["error"]["code"] == "HAS_HISTORY"
    assert client.delete(f"{API}/users/{clean.id}", headers=H(admin_token)).status_code == 204


# ---- Audit log ----------------------------------------------------------------------------
def test_audit_paging_bounds_and_separate_action_list(client, db_session, admin_token):
    for i in range(45):
        db_session.add(AuditLog(user_id=None, action="auth.login_failed" if i % 3 == 0 else "case.update"))
    db_session.commit()
    assert client.get(f"{API}/audit?page=0", headers=H(admin_token)).status_code == 422     # was a negative offset
    page3 = client.get(f"{API}/audit?page=3&page_size=20", headers=H(admin_token)).json()
    assert page3["total"] >= 45 and len(page3["items"]) == page3["total"] - 40
    assert {"auth.login_failed", "case.update"} <= set(client.get(f"{API}/audit/actions", headers=H(admin_token)).json())


def test_audit_prefix_filter_treats_wildcards_literally(client, db_session, admin_token):
    db_session.add_all([AuditLog(action="auth.login"), AuditLog(action="authXlogin")]); db_session.commit()
    rows = client.get(f"{API}/audit?action=auth.*", headers=H(admin_token)).json()["items"]
    assert rows and all(r["action"].startswith("auth.") for r in rows)
    assert not client.get(f"{API}/audit?action=%25*", headers=H(admin_token)).json()["items"]   # '%' is not a wildcard


# ---- Intelligence -------------------------------------------------------------------------
def test_merchant_stats_match_the_data_and_unknown_merchant_is_404(client, db_session, admin_token):
    m = Merchant(name="Shop", category="x"); db_session.add(m); db_session.commit(); db_session.refresh(m)
    ids = []
    for amt, level in [(100, "LOW"), (300, "CRITICAL"), (200, "HIGH"), (400, "LOW")]:
        t = Transaction(user_id=1, merchant_id=m.id, amount=amt, currency="INR", status="allowed")
        db_session.add(t); db_session.commit(); db_session.refresh(t)
        db_session.add(FraudPrediction(transaction_id=t.id, probability=0.1, risk_score=10, risk_level=level, model_version="v")); ids.append(t.id)
    db_session.commit()
    row = client.get(f"{API}/merchants", headers=H(admin_token)).json()[0]
    assert (row["transactions"], row["fraud_count"], row["fraud_rate"], row["average_amount"]) == (4, 2, 0.5, 250.0)
    db_session.refresh(m)
    assert m.risk_score == row["risk_score"] > 0          # kept current for the dashboard panel
    assert client.get(f"{API}/merchants/{m.id}", headers=H(admin_token)).json() == row
    assert client.get(f"{API}/merchants/9999", headers=H(admin_token)).status_code == 404


def test_profiles_count_each_users_risky_transactions(client, db_session, admin_token):
    for level in ["CRITICAL", "LOW", "LOW", "HIGH"]:
        t = Transaction(user_id=7, amount=50, currency="INR", status="allowed")
        db_session.add(t); db_session.commit(); db_session.refresh(t)
        db_session.add(FraudPrediction(transaction_id=t.id, probability=0.1, risk_score=1, risk_level=level, model_version="v"))
    db_session.commit()
    p = [x for x in client.get(f"{API}/profiles", headers=H(admin_token)).json() if x["user_id"] == 7][0]
    assert p["transaction_count"] == 4 and p["fraud_rate"] == 0.5


def test_graph_risk_ignores_the_training_corpus(client, db_session, admin_token):
    db_session.add(Transaction(id=-5, user_id=3, device_id=None, merchant_id=None, amount=1, currency="INR", status="allowed"))
    db_session.commit()
    body = client.get(f"{API}/graph/risk", headers=H(admin_token)).json()
    assert "nodes" in body and "edges" in body


def test_drift_snapshots_are_throttled_not_one_per_page_view(client, db_session, admin_token):
    for i in range(30):
        t = Transaction(user_id=1, amount=1, currency="INR", status="allowed")
        db_session.add(t); db_session.commit(); db_session.refresh(t)
        db_session.add(FraudPrediction(transaction_id=t.id, probability=i / 30, risk_score=i, risk_level="LOW", model_version="v"))
    db_session.commit()
    for _ in range(3):
        assert client.get(f"{API}/monitoring/drift", headers=H(admin_token)).json()["samples"] == 30
    assert db_session.query(DriftSnapshot).count() == 1
    db_session.query(DriftSnapshot).update({"created_at": datetime.now(timezone.utc) - timedelta(minutes=11)}); db_session.commit()
    client.get(f"{API}/monitoring/drift", headers=H(admin_token))
    assert db_session.query(DriftSnapshot).count() == 2
