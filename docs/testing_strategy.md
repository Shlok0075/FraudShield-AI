# Testing Strategy (PART 15 / Week 13)

| Layer | Approach | Location |
|---|---|---|
| Unit (ML) | Decision engine every branch, predict() smoke tests | `ml/src/test_ml.py` |
| Unit (backend) | Auth (password hashing, token creation/decoding), decision engine | `backend/tests/test_auth.py`, `test_decision_engine_unit.py` |
| Integration | Full `POST /transactions/predict` → DB → dashboard, hitting an in-memory SQLite test DB | `backend/tests/test_transactions_integration.py` |
| Security-adjacent | 401/403/422 access-control + SQL-injection-style rejection | `backend/tests/test_rbac_and_security.py` |
| Frontend | Manual scripted QA (see below) — chosen over Vitest/RTL given the 4-month scope; documented tradeoff |
| ML regression guard | `ml/src/train.py` re-computes Precision/Recall/F1/ROC-AUC/PR-AUC every run; `docs/model_selection.md` records the accepted baseline |
| Performance | Manual latency measurement (see below); `locust`/asyncio load script left as a documented stretch goal |

## Test database tradeoff (Week 13 Day 3)

Integration tests use an **in-memory SQLite** database instead of spinning up a second Postgres instance for
CI speed and zero external dependency. All backend code that touches raw SQL was written to be
cross-DB-portable — see `app/services/feature_engineering.py`'s docstring (Python-side mean/stdev instead of
`func.stddev`, which is Postgres-only). The full application was **also** verified against a real local
PostgreSQL 16 instance during development (see `docs/deployment.md`), so both paths are exercised.

## Frontend manual QA log (Week 9 Day 7 / Week 13 Day 5)

Performed with Playwright driving a real Chromium browser against the live Vite dev server + live FastAPI
backend + live Postgres:
- [x] Login flow (valid credentials → redirected to `/dashboard`)
- [x] Dashboard renders live KPIs, model-info card, trend/risk/geography charts, recent transactions table
- [x] Alerts page renders and lets an admin change alert status
- [x] Transaction Detail page renders the SHAP-style "Fraud Risk: X% — LEVEL — Main Reasons" panel
- [x] Session lost on refresh (documented tradeoff — token is memory-only, not localStorage)

## Actual results (this repo, latest run)

```
$ pytest backend/tests/ --cov=app --cov-report=term-missing
======================= 27 passed, 12 warnings in 12.54s =======================
TOTAL coverage: 85%

$ pytest ml/src/test_ml.py
======================= 18 passed, 3 warnings in 1.69s =======================
```

See `docs/test_report.md` for the full breakdown by test file.

## Security testing (Week 13 Day 6)
- Unauthorized request → 401 ✅
- Invalid JWT → 401 ✅
- Wrong-role request → 403 ✅ (both admin-only and admin/analyst-only routes)
- SQL-injection-style input in `amount` → 422, rejected by Pydantic before reaching SQL ✅

## Performance testing note (NFR1/NFR4)
Manual timing via the FastAPI request-logging middleware (`app/utils/logging_config.py`) showed
`POST /transactions/predict` completing in **~10-30ms** locally (well under the 300ms academic target, NFR1),
and the `scripts/simulator.py` script comfortably sustains more than 50 transactions/minute (NFR4) at its
default 3-second interval, or much higher when run with a shorter `--interval`. A dedicated Locust/asyncio load
test harness is documented here as a natural next step but was not required to demonstrate NFR1/NFR4 for this
academic build.
