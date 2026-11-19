"""Regression tests for the slow Alerts / Cases pages.

- /alerts used to return every row (payload and React render grew without bound).
- /cases used to run one extra query per case (an N+1): 5,000 cases = 5,002 queries.
"""
from sqlalchemy import event

from app.models.case import CaseNote, FraudCase
from app.models.fraud_alert import FraudAlert


def _seed(db, n_cases, notes_each=2):
    alerts = [FraudAlert(transaction_id=i, severity="HIGH", status="open") for i in range(1, n_cases + 1)]
    db.add_all(alerts)
    db.commit()
    cases = [FraudCase(alert_id=a.id, status="open", priority="high") for a in alerts]
    db.add_all(cases)
    db.commit()
    db.add_all([CaseNote(case_id=c.id, author_id=1, note=f"note {k}") for c in cases for k in range(notes_each)])
    db.commit()


def _count_queries(client, db, url, token):
    n = []
    listener = lambda *a: n.append(1)  # noqa: E731
    event.listen(db.get_bind(), "before_cursor_execute", listener)
    try:
        resp = client.get(url, headers={"Authorization": f"Bearer {token}"})
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", listener)
    return resp, len(n)


def test_alerts_are_paginated_without_overlap(client, db_session, admin_token):
    _seed(db_session, 130, notes_each=0)
    h = {"Authorization": f"Bearer {admin_token}"}
    first = client.get("/api/v1/alerts", headers=h).json()
    assert len(first) == 100                                   # default page size, not "all rows"
    second = client.get("/api/v1/alerts?limit=100&offset=100", headers=h).json()
    assert len(second) == 30
    ids = [a["id"] for a in first + second]
    assert len(ids) == len(set(ids)) == 130                    # no overlap, nothing skipped


def test_alerts_limit_is_validated(client, admin_token):
    h = {"Authorization": f"Bearer {admin_token}"}
    assert client.get("/api/v1/alerts?limit=0", headers=h).status_code == 422
    assert client.get("/api/v1/alerts?limit=501", headers=h).status_code == 422
    assert client.get("/api/v1/alerts?offset=-1", headers=h).status_code == 422


def test_cases_list_query_count_does_not_grow_with_case_count(client, db_session, admin_token):
    _seed(db_session, 5)
    _, small = _count_queries(client, db_session, "/api/v1/cases", admin_token)
    _seed(db_session, 40)
    resp, large = _count_queries(client, db_session, "/api/v1/cases", admin_token)
    assert len(resp.json()) == 45
    assert large == small                                      # constant, no N+1
    assert large <= 9                                         # notes + alerts + txns batched, plus auth


def test_cases_list_returns_notes_in_order_and_paginates(client, db_session, admin_token):
    _seed(db_session, 12, notes_each=3)
    h = {"Authorization": f"Bearer {admin_token}"}
    rows = client.get("/api/v1/cases?limit=5", headers=h).json()
    assert len(rows) == 5 and all(len(r["notes"]) == 3 for r in rows)
    assert [n["note"] for n in rows[0]["notes"]] == ["note 0", "note 1", "note 2"]
    rest = client.get("/api/v1/cases?limit=100&offset=5", headers=h).json()
    assert len(rest) == 7
    assert not {r["id"] for r in rows} & {r["id"] for r in rest}
