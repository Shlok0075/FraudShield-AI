# Risk Scoring & Decision Engine (Week 6)

> **Academic disclaimer:** this is a demonstration policy for a student prototype, not a real banking
> authorization/compliance policy.

## Formula

```
risk_score = round(fraud_probability * 100)      # clamped to [0, 100]

  0-29   -> LOW
  30-59  -> MEDIUM
  60-79  -> HIGH
  80-100 -> CRITICAL
```

Thresholds are **configurable constants** (`ml/src/decision_engine.py::RISK_THRESHOLDS`), not magic numbers
scattered through route handlers — they can be retuned without touching the API layer.

## Decision table

| risk_score | risk_level | Decision | Alert created? |
|---|---|---|---|
| 0-29 | LOW | Allow | No |
| 30-59 | MEDIUM | Monitor | Yes (severity=MEDIUM) |
| 60-79 | HIGH | Flag | Yes (severity=HIGH) |
| 80-100 | CRITICAL | Critical Alert | Yes (severity=CRITICAL) |

Implemented as pure, independently unit-tested functions (`ml/src/decision_engine.py`,
`backend/tests/test_decision_engine_unit.py` — every branch covered).

## Explainability (SHAP)

`ml/src/predict.py::explain_prediction()` uses `shap.TreeExplainer` for the tree-based model (falls back to
`feature_importances_`/`coef_` for other model types) to return the top-4 contributing features with direction:

```
Fraud Risk: 86%
Risk Level: CRITICAL
Main Reasons:
  - Anonymized pattern signal V12  (increases risk)
  - Anonymized pattern signal V18  (increases risk)
  - Unusual transaction amount     (decreases risk, in this example)
  - Anonymized pattern signal V4   (decreases risk)
```
(Real output captured from this project's running system — see `docs/testing_strategy.md`.)

Always presented as a **model-derived statistical indicator, not proof of fraud** — a human must review before
any real action is taken (enforced in the UI copy on the Transaction Detail page).
