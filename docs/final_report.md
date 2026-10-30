# FraudShield AI — Final Project Report

**Intelligent Online Transaction Fraud Detection and Real-Time Monitoring System**
B.Tech Final Year Project — Academic Prototype

---

## 1. Title Page
FraudShield AI — Intelligent Online Transaction Fraud Detection and Real-Time Monitoring System.
*(Fill in: your name, guide name, college, department, academic year.)*

## 2. Certificate
*(Institution-specific template — insert as required by your department.)*

## 3. Declaration
*(Standard academic-integrity declaration — insert as required by your department.)*

## 4. Acknowledgement
*(Personalize — thank your guide, HOD, family, etc.)*

## 5. Abstract
FraudShield AI is a full-stack academic prototype that detects fraudulent online transactions using a
supervised machine learning model and surfaces suspicious activity through a real-time web dashboard. The
system combines three engineering disciplines — applied ML, backend/API engineering, and real-time web
development. A synthetic dataset matching the schema of the well-known ULB Credit Card Fraud dataset
(~120,000 transactions, 0.17% fraud) was used to train and compare Logistic Regression, Random Forest, and
XGBoost under two imbalance-handling strategies (class-weighting and SMOTE); XGBoost with class-weighting was
selected (precision 0.7647, PR-AUC 0.4324). The trained model is served through a FastAPI backend with
JWT-based authentication and role-based access control (Admin/Analyst/User), persisting all data in
PostgreSQL via SQLAlchemy and Alembic migrations. Real-time alerts are pushed to a React/Tailwind dashboard via
Socket.IO, with SHAP-based explainability shown on a per-transaction investigation page. The system was
verified end-to-end — 45 automated tests passing (85% backend coverage), and live browser screenshots
confirming the full login → dashboard → alert → investigation flow — with security hardening (bcrypt, rate
limiting, RBAC, parameterized queries) and full API/architecture documentation.

## 6. Table of Contents
See this file's headings; each chapter below maps to real, runnable code in this repository.

## 7. Introduction
See `docs/requirements.md` §1 (Executive Overview).

## 8. Problem Statement
See `docs/requirements.md` §2.

## 9. Objectives
See `docs/requirements.md` §3.

## 10. Literature Survey
Fraud detection is a long-studied application of anomaly detection and supervised classification.
Representative approaches surveyed for this project (summarized in your own words, cite properly in your
final institutional submission):
1. **Rule-based / expert systems** — early fraud systems relying on hand-written thresholds; rigid, easy to
   reverse-engineer, high false-positive rates.
2. **Supervised classification (Logistic Regression, tree ensembles)** — the approach this project takes;
   strong when labeled historical data exists, as it does academically (Kaggle's ULB dataset).
3. **Unsupervised/anomaly-detection approaches (Isolation Forest, Autoencoders)** — useful when labels are
   scarce; not the primary approach here since a labeled dataset was available.
4. **Ensemble/gradient-boosting methods (XGBoost, LightGBM)** — widely reported as strong tabular-data
   baselines in fraud-detection literature, matching this project's own empirical finding.
5. **Graph-based fraud detection** — models transaction networks to catch collusion rings; explicitly out of
   scope here (Future Scope, §32).
6. **Explainable AI in finance (SHAP)** — increasingly required for auditability/regulatory trust; adopted here
   for per-prediction explanations.

## 11. Existing System
Rule-based checks ("block if amount > X", "block if country ≠ home country") — static, easy to bypass by
staying under thresholds, and generate high false-positive rates that erode user trust.

## 12. Proposed System
A supervised ML model producing a continuous probability score, mapped through a configurable risk-scoring and
decision engine, with human-in-the-loop review via a real-time investigation dashboard (see
`docs/architecture.md`).

## 13. System Requirements
See `docs/requirements.md` §5-6 (Functional / Non-Functional Requirements) — all 10 FRs and 6 NFRs implemented
and verified.

## 14. Technology Stack
See `README.md` "Technology Stack" section, mirroring PART 2 of the handbook this project follows.

## 15. System Architecture
See `docs/architecture.md`.

## 16. Data Flow
See `docs/uml_diagrams.md` (Data Flow Diagram, Level 1).

## 17. UML Diagrams
See `docs/uml_diagrams.md` (Use Case, Sequence, Class, Activity, Component diagrams — all as renderable Mermaid).

## 18. ER Diagram
See `docs/uml_diagrams.md` (Class Diagram section mirrors the ER relationships) and PART 11-style schema below.

## 19. Database Design
8 tables: `users`, `merchants`, `devices`, `transactions`, `fraud_predictions`, `fraud_alerts`, `audit_logs`,
`model_versions`. Full column-level schema implemented in `backend/app/models/*.py`, versioned via Alembic
(`backend/alembic/versions/`). See the "why these tables and not more" rationale in each model's docstring.

## 20. ML Methodology
Dataset → Cleaning → EDA → Feature Engineering → Train/Test Split → Imbalance Handling → Train (3 algorithms) →
Evaluate → Select Best → Serialize (joblib) → Load into backend at startup. See `ml/src/train.py`.

## 21. Feature Engineering
See `docs/feature_plan.md`.

## 22. Model Training
See `ml/src/train.py` and `ml/notebooks/04_baseline_models.ipynb`, `05_tuning.ipynb`.

## 23. Model Evaluation
See `docs/model_selection.md` — full 6-variant comparison table with real numbers.

## 24. Backend Implementation
FastAPI app (`backend/app/main.py`) with routers for auth, transactions, alerts, dashboard, reports, audit,
users; SQLAlchemy ORM; Alembic migrations; JWT auth + RBAC; python-socketio for real-time push; slowapi for
rate limiting.

## 25. Frontend Implementation
React (Vite) + Tailwind CSS v4 + Recharts + Axios + socket.io-client. Pages: Login, Dashboard, Alerts,
Transaction Detail, Audit Log, Users. See `frontend/src/`.

## 26. Real-Time Monitoring
See `docs/realtime_flow.md`.

## 27. Security
See `docs/security.md`.

## 28. Testing
See `docs/testing_strategy.md` and `docs/test_report.md` — 45/45 tests passing.

## 29. Results
Final model (XGBoost, class_weight='balanced'): **Precision 0.7647, Recall 0.3171, F1 0.4483, ROC-AUC 0.9139,
PR-AUC 0.4324** on a held-out test set of 24,000 transactions (28 of which were fraud). Example flagged
transaction (captured live from this running system):
```
Transaction #9 — Amount: INR 77.23 — Location: Hyderabad
Fraud Risk: 86% — CRITICAL
Main Reasons: Anonymized pattern signal V12 (↑), Anonymized pattern signal V18 (↑),
              Unusual transaction amount (↓), Anonymized pattern signal V4 (↓)
```
Dashboard, alerts, and transaction-detail screenshots captured during development (see the project's
`screenshots/` folder and this report's accompanying deliverables).

## 30. Screenshots
See `screenshots/` (EDA plot) and the dashboard/alerts/transaction-detail screenshots captured during
Playwright-driven manual QA (Week 13 Day 5 in `docs/testing_strategy.md`).

## 31. Limitations
- Trained on **public/synthetic data**, not connected to real banking rails — not representative of real-world
  fraud patterns today (see `docs/dataset_choice.md`).
- The selected model catches only **~32% of fraud** (recall 0.3171) at the benefit of high precision (76%) —
  a deliberate, honest tradeoff, not a hidden flaw.
- False positives cannot be fully eliminated; mitigated via human-in-the-loop review, not automatic blocking.
- Fraud patterns evolve over time in the real world; this prototype does not implement continuous retraining
  (see `docs/model_monitoring.md`).
- Frontend session is lost on page refresh (token kept in memory, not `localStorage`) — a documented
  security-vs-convenience tradeoff.

## 32. Future Scope
Deep Learning / Graph Neural Networks for relationship fraud, streaming architecture (Kafka), Redis caching,
advanced anomaly detection, online/continual learning, model drift detection, federated learning, multi-model
ensembles, behavioral biometrics, device-fingerprinting SDKs, risk-based authentication, real payment-gateway
integration, and full PCI-DSS compliance — all explicitly out of scope for this 4-month academic prototype.

## 33. Conclusion
FraudShield AI successfully demonstrates an end-to-end, production-shaped (if academically-scoped) fraud
detection pipeline: a rigorously compared and honestly-evaluated ML model, a secure and tested REST/WebSocket
backend, and a real-time investigative dashboard — verified running together against a real PostgreSQL
database with live browser screenshots, not just described on paper.

## 34. References
1. Dal Pozzolo, A. et al. — "Credit Card Fraud Detection: A Realistic Modeling and a Novel Learning Strategy"
   (the dataset this project's schema is modeled on).
2. Chen, T. & Guestrin, C. — "XGBoost: A Scalable Tree Boosting System", KDD 2016.
3. Lundberg, S. & Lee, S. — "A Unified Approach to Interpreting Model Predictions" (SHAP), NeurIPS 2017.
4. Chawla, N. et al. — "SMOTE: Synthetic Minority Over-sampling Technique", JAIR 2002.
5. FastAPI, SQLAlchemy, React, and PostgreSQL official documentation.
*(Add any papers you personally read for your Literature Survey with full citations per your institution's format.)*
