# FraudShield AI — Final Presentation

## Slide 1 — Title
FraudShield AI: Explainable Hybrid AI for Real-Time Online Transaction Fraud Detection and Risk Monitoring

## Slide 2 — Problem
- Online fraud is rare but high-impact.
- Static rules are difficult to maintain and can create false positives.
- Fraud patterns evolve over time.

## Slide 3 — Objectives
- Detect suspicious transactions in real time.
- Combine ML, anomaly detection, behavioral signals and rules.
- Explain decisions.
- Support analyst investigation and feedback.
- Monitor the deployed model.

## Slide 4 — Existing vs Proposed
Existing: static rules / isolated classifier.
Proposed: point-in-time features → ML + anomaly + behavior + rules → explainable risk → case → feedback.

## Slide 5 — Architecture
Show the complete transaction-to-dashboard pipeline.

## Slide 6 — Feature Engineering
Show amount anomaly, velocity, timing, device and location features.

## Slide 7 — ML Models
Logistic Regression, Random Forest, XGBoost, Isolation Forest and Hybrid.

## Slide 8 — Hybrid Risk Engine
ML score + anomaly score + behavior score + rules → 0–100 risk score → ALLOW/REVIEW/BLOCK.

## Slide 9 — Explainability
Show human-readable reasons and SHAP contributions.

## Slide 10 — Real-Time System
React dashboard + FastAPI + WebSocket + PostgreSQL.

## Slide 11 — Investigation
Alert → case → analyst notes → decision → feedback.

## Slide 12 — Model Lifecycle
Prediction → feedback → candidate model → validation → registry → approved production model.

## Slide 13 — Results
Use the synthetic behavioral benchmark table from `docs/phase9_final_submission.md`. Explicitly state that it is synthetic.

## Slide 14 — Security
JWT, RBAC, bcrypt, rate limiting, validation, parameterized queries, audit logs.

## Slide 15 — Monitoring
Prediction drift / PSI, model version, inference latency, risk distribution.

## Slide 16 — Demo Scenarios
Account takeover, card testing, transaction burst, new device/location change, transaction splitting, fraud ring.

## Slide 17 — Limitations & Future Scope
Public/ synthetic data limitations, richer device/location benchmark, full concept drift, GNN research, automated retraining with approval.

## Slide 18 — Conclusion
FraudShield demonstrates an end-to-end explainable fraud-monitoring architecture rather than only a classifier.
