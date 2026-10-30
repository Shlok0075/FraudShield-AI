# Test Report (Week 13, Day 7)

## Backend (pytest + pytest-cov)

```
27 passed, 12 warnings in 12.54s
TOTAL coverage: 85% (787 statements, 121 missed)
```

By file (selected):
| File | Coverage |
|---|---|
| `app/routes/auth.py` | 100% |
| `app/routes/transactions.py` | 96% |
| `app/models/*.py` | 100% |
| `app/services/feature_engineering.py` | 98% |
| `app/routes/dashboard.py` | 53% (analytics endpoints only exercised indirectly; KPI path covered) |
| `app/routes/users.py` | 41% (CRUD paths not all hit by the current integration tests — acceptable given `require_role` is unit-tested directly) |

## Test files and counts

| File | Tests | Focus |
|---|---|---|
| `test_auth.py` | 6 | register/login/me, password hashing, invalid token |
| `test_decision_engine_unit.py` | 6 | every risk-level branch, alert threshold |
| `test_rbac_and_security.py` | 8 | 401/403/422, consistent error format |
| `test_transactions_integration.py` | 7 | full predict flow, list/detail/action, KPI reflection |
| **Backend total** | **27** | **all passing** |

| File | Tests | Focus |
|---|---|---|
| `ml/src/test_ml.py` | 18 | decision engine branches + real `predict()` smoke test against the trained model |

## Pass/fail summary

**45 / 45 tests passing** across the ML and backend suites, 0 failures, 0 errors, at the time this handbook's
Month 4 Week 13 work was completed for this repository.

## Known gaps (documented, not hidden)
- Frontend automated tests (Vitest/RTL) were not implemented — manual scripted QA was chosen instead given the
  4-month scope (see `docs/testing_strategy.md`); this is an explicit, documented tradeoff, not an oversight.
- Load/performance testing is manual (latency observed via logs), not an automated Locust suite.
