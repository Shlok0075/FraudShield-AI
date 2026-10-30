"""
FraudShield AI - live feed, live-only dashboard scoping, and audit trail
=======================================================================
Covers the behaviour introduced when the dashboard was wired to a
self-starting feed and the login/audit section was reworked:

* the built-in feed runs the same pipeline the HTTP endpoint does
* dashboard KPIs/trends/risk/geography count live traffic only
* PaySim corpus rows are still reachable, but never inflate live numbers
* successful AND failed logins are audited, with no credentials stored
* audit entries expose the actor email and a resolved target label
"""
import asyncio

from app.config.settings import settings
from app.models import FraudPrediction, Transaction
from app.services.live_feed import LiveFeed, build_payload
from app.services.prediction_pipeline import ingest_transaction

CORPUS_ID = -10_000_000


def _predict(client, token, **overrides):
    payload = {"user_id": 1, "amount": 900.0, "device_id": "dev-1",
               "location": "Mumbai", "payment_method": "card"}
    payload.update(overrides)
    r = client.post("/api/v1/transactions/predict", json=payload,
                    headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return r.json()


def _role_of(client, token):
    """/auth/login returns only a token, so read the role from /auth/me."""
    return client.get("/api/v1/auth/me",
                      headers={"Authorization": f"Bearer {token}"}).json()["role"]


# --------------------------------------------------------------------------
# 1. The feed itself
# --------------------------------------------------------------------------

def test_build_payload_is_valid_for_every_scenario():
    """Every scenario the feed can pick must produce a scorable payload."""
    from app.services.live_feed import SCENARIOS

    for name, _weight in SCENARIOS:
        p = build_payload(name)
        assert p["amount"] > 0, name
        assert isinstance(p["user_id"], int), name
        assert p["device_id"] and p["location"] and p["payment_method"], name


def test_feed_payload_scores_through_the_real_pipeline(db_session):
    """A fed payload must produce a real prediction, not just a row.

    This is the property that matters: the feed calls the same
    ingest_transaction() the HTTP endpoint uses, so live traffic is scored,
    persisted and (where warranted) alerted exactly like real traffic.
    """
    result = asyncio.run(ingest_transaction(db_session, build_payload("high_value")))

    assert result["transaction_id"] >= 0, "live ids must not collide with corpus ids"
    pred = db_session.query(FraudPrediction).filter_by(
        transaction_id=result["transaction_id"]).one()
    assert pred.risk_score is not None
    assert pred.risk_level in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert 0.0 <= pred.probability <= 1.0


def test_feed_survives_a_failing_transaction(monkeypatch):
    """One bad payload must not kill the feed -- it counts the error and continues.

    Otherwise a single transient DB error silently freezes the dashboard for
    the rest of the session, which is precisely the failure mode the feed
    exists to prevent.
    """
    feed = LiveFeed()
    monkeypatch.setattr(settings, "LIVE_FEED_INTERVAL_SECONDS", 0.2)

    calls = {"n": 0}

    async def flaky(scenario):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("transient failure")
        return {"transaction_id": calls["n"] - 1}

    monkeypatch.setattr(feed, "_emit_one", flaky)

    async def drive():
        task = asyncio.create_task(feed._run())
        try:
            while calls["n"] < 3:          # two successes after the failure
                await asyncio.sleep(0.01)
        finally:
            feed._stopping.set()
            await asyncio.wait_for(task, 5)

    asyncio.run(drive())

    assert feed.errors == 1
    assert "transient failure" in feed.last_error
    assert calls["n"] >= 3, "feed stopped instead of continuing past the error"


# --------------------------------------------------------------------------
# 2. Dashboard scoping: live vs corpus
# --------------------------------------------------------------------------

def test_kpis_start_from_zero_and_exclude_the_corpus(client, admin_token):
    """A clean database must read 0 total transactions, not the corpus size."""
    k = client.get("/api/v1/dashboard/kpis",
                   headers={"Authorization": f"Bearer {admin_token}"}).json()

    assert k["total_transactions"] == 0
    assert k["scored_transactions"] == 0
    # No corpus loaded, so the ground-truth block is omitted entirely rather
    # than reported as zeros -- the live figures must not depend on it either way.
    assert "paysim_total" not in k


def test_live_transactions_count_up_and_corpus_stays_out(client, admin_token, db_session):
    for _ in range(3):
        _predict(client, admin_token)

    # A corpus row -- a negative id -- must never reach the live figures.
    db_session.add(Transaction(
        id=CORPUS_ID, user_id=999, amount=500.0, device_id="dev-corpus",
        location="Nowhere", payment_method="card"))
    db_session.commit()

    k = client.get("/api/v1/dashboard/kpis",
                   headers={"Authorization": f"Bearer {admin_token}"}).json()

    assert k["total_transactions"] == 3, "corpus row leaked into the live total"
    assert k["scored_transactions"] == 3
    assert k["fraud_count"] + k["suspicious_count"] + k["safe_count"] == 3


def test_risk_and_geographic_panels_are_live_scoped(client, admin_token):
    _predict(client, admin_token)
    _predict(client, admin_token, amount=250_000.0, location="Lagos")

    k = client.get("/api/v1/dashboard/kpis",
                   headers={"Authorization": f"Bearer {admin_token}"}).json()
    risk = client.get("/api/v1/dashboard/risk-distribution",
                      headers={"Authorization": f"Bearer {admin_token}"}).json()
    geo = client.get("/api/v1/dashboard/geographic",
                     headers={"Authorization": f"Bearer {admin_token}"}).json()

    assert sum(b["value"] for b in risk) == k["total_transactions"]
    assert sum(b["value"] for b in geo) == k["total_transactions"]


def test_trends_report_live_scope_and_corpus_trends_are_separate(client, admin_token):
    _predict(client, admin_token)

    tr = client.get("/api/v1/dashboard/trends?granularity=hour",
                    headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert tr["scope"] == "live"
    assert sum(p["transactions"] for p in tr["series"]) == 1

    # corpus-trends stays available for training analytics, explicitly labelled.
    corpus = client.get("/api/v1/dashboard/corpus-trends",
                        headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert corpus["scope"] == "corpus"
    assert corpus["available"] is False  # empty corpus in the test DB


# --------------------------------------------------------------------------
# 3. Audit trail
# --------------------------------------------------------------------------

def test_successful_login_is_audited_with_actor_and_target(client):
    client.post("/api/v1/auth/register", json={
        "email": "auditor@fraudshield.ai", "password": "StrongPass123!", "role": "admin"})
    client.post("/api/v1/auth/login", json={
        "email": "auditor@fraudshield.ai", "password": "StrongPass123!"})

    token = client.post("/api/v1/auth/login", json={
        "email": "auditor@fraudshield.ai", "password": "StrongPass123!"}).json()["access_token"]

    audit = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {token}"}).json()
    logins = [r for r in audit["items"] if r["action"] == "auth.login"]

    assert logins, "successful logins must be audited"
    row = logins[0]
    assert row["user_email"] == "auditor@fraudshield.ai"
    assert row["target_label"] == "user auditor@fraudshield.ai"
    assert "role" in row["detail"]


def test_failed_logins_are_audited_for_both_failure_modes(client):
    client.post("/api/v1/auth/register", json={
        "email": "target@fraudshield.ai", "password": "StrongPass123!", "role": "admin"})
    token = client.post("/api/v1/auth/login", json={
        "email": "target@fraudshield.ai", "password": "StrongPass123!"}).json()["access_token"]

    # wrong password for a real account
    client.post("/api/v1/auth/login", json={
        "email": "target@fraudshield.ai", "password": "DefinitelyWrong123!"})
    # unknown account
    client.post("/api/v1/auth/login", json={
        "email": "ghost@fraudshield.ai", "password": "StrongPass123!"})

    audit = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {token}"}).json()
    failures = [r for r in audit["items"] if r["action"] == "auth.login_failed"]
    details = " | ".join(r["detail"] or "" for r in failures)

    assert len(failures) == 2, failures
    assert "ghost@fraudshield.ai" in details, "attempted email must be recorded"
    assert "target@fraudshield.ai" in details


def test_audit_never_stores_credentials(client, admin_token):
    secret = "DoNotLogMe123!"
    client.post("/api/v1/auth/login", json={
        "email": "nobody@fraudshield.ai", "password": secret})

    audit = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {admin_token}"}).json()
    blob = repr(audit["items"])
    assert secret not in blob
    assert "password" not in blob.lower()


def test_audit_exposes_action_filters_and_prefix_search(client, admin_token):
    client.post("/api/v1/auth/login", json={
        "email": "nobody@fraudshield.ai", "password": "nope"})

    audit = client.get("/api/v1/audit", headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert "auth.login" in audit["actions"]
    assert "auth.login_failed" in audit["actions"]

    filtered = client.get("/api/v1/audit?action=auth*",
                          headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert filtered["total"] > 0
    assert all(r["action"].startswith("auth") for r in filtered["items"])


def test_audit_requires_admin(client, user_token):
    assert client.get("/api/v1/audit",
                      headers={"Authorization": f"Bearer {user_token}"}).status_code == 403


def test_role_changes_are_audited(client, admin_token):
    created = client.post("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"},
                          json={"email": "auditee@fraudshield.ai",
                                "password": "StrongPass123!", "role": "analyst"})
    assert created.status_code == 201, created.text
    uid = created.json()["id"]

    r = client.patch(f"/api/v1/users/{uid}/role",
                     headers={"Authorization": f"Bearer {admin_token}"},
                     json={"role": "user"})
    assert r.status_code == 200
    assert r.json()["role"] == "user"

    audit = client.get("/api/v1/audit?action=user*",
                       headers={"Authorization": f"Bearer {admin_token}"}).json()
    actions = {r["action"] for r in audit["items"]}
    assert "user.create" in actions
    assert "user.update_role" in actions


# --------------------------------------------------------------------------
# 4. Users persist and stay enforced
# --------------------------------------------------------------------------

def test_created_user_persists_and_can_log_in(client, admin_token):
    created = client.post("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"},
                          json={"email": "persist@fraudshield.ai",
                                "password": "StrongPass123!", "role": "analyst"})
    assert created.status_code == 201

    r = client.post("/api/v1/auth/login", json={
        "email": "persist@fraudshield.ai", "password": "StrongPass123!"})
    assert r.status_code == 200
    assert _role_of(client, r.json()["access_token"]) == "analyst"

    # the account is real, not just echoed back
    listing = client.get("/api/v1/users",
                         headers={"Authorization": f"Bearer {admin_token}"}).json()
    assert any(u["email"] == "persist@fraudshield.ai" for u in listing)


def test_role_update_survives_a_fresh_read(client, admin_token):
    created = client.post("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"},
                          json={"email": "promote@fraudshield.ai",
                                "password": "StrongPass123!", "role": "user"})
    uid = created.json()["id"]

    client.patch(f"/api/v1/users/{uid}/role",
                 headers={"Authorization": f"Bearer {admin_token}"}, json={"role": "admin"})

    # re-read the role from storage, not from the PATCH response
    listing = client.get("/api/v1/users",
                         headers={"Authorization": f"Bearer {admin_token}"}).json()
    stored = next(u for u in listing if u["id"] == uid)
    assert stored["role"] == "admin"

    # and the new privilege actually applies on a fresh login
    promoted = client.post("/api/v1/auth/login", json={
        "email": "promote@fraudshield.ai", "password": "StrongPass123!"}).json()["access_token"]
    assert _role_of(client, promoted) == "admin"
    assert client.get("/api/v1/audit",
                      headers={"Authorization": f"Bearer {promoted}"}).status_code == 200


def test_duplicate_email_is_rejected(client, admin_token):
    body = {"email": "dupe@fraudshield.ai", "password": "StrongPass123!", "role": "user"}
    assert client.post("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"},
                       json=body).status_code == 201
    second = client.post("/api/v1/users", headers={"Authorization": f"Bearer {admin_token}"},
                         json=body)
    assert second.status_code in (400, 409)
    assert second.json()["error"]["code"] == "EMAIL_EXISTS"
