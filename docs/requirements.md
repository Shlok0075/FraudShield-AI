# FraudShield AI — Requirements (SRS-style)

## 1. Executive Overview
FraudShield AI is a web-based platform that ingests transaction data, scores each transaction for fraud risk
using a trained Machine Learning model, and surfaces suspicious activity to an administrator through a
real-time dashboard.

## 2. Problem Statement
Rule-based fraud systems ("block if amount > X") are rigid, easy to bypass, and generate excessive false
positives. A learning-based system recognizes complex, evolving patterns across many features simultaneously
and assigns a probabilistic risk score instead of a binary yes/no, enabling smarter human review.

## 3. Objectives
- Build a supervised ML model that classifies transactions as fraud/legitimate with a probability score.
- Engineer fraud-relevant features (velocity, device change, location change).
- Expose the model via a REST API that scores transactions in real time.
- Persist transactions, predictions, and alerts in a relational database.
- Push real-time alerts to a live admin dashboard via WebSockets.
- Provide investigation tooling: drill into a transaction, see why it was flagged, mark reviewed/resolved/false-positive.
- Implement authentication, role-based access, and basic security hygiene.
- Document, test, and deploy the system as a demonstrable academic prototype.

## 4. Scope

**In scope:** single ML model (3 algorithms compared), FastAPI backend, PostgreSQL database, React dashboard,
WebSocket alerts, JWT auth with Admin/Analyst/User roles, synthetic transaction simulator, CSV reporting, audit
logging, basic rate limiting and input validation.

**Out of scope (Future Scope):** Kafka/streaming infra, Kubernetes, microservices, deep learning, federated
learning, real payment gateway integration, regulatory compliance (PCI-DSS), multi-model ensembles in
production, device fingerprinting SDKs.

## 5. Functional Requirements

| ID | Requirement |
|---|---|
| FR1 | User can log in (JWT); roles: Admin, Analyst, User (viewer) |
| FR2 | System can accept a transaction (via API or simulator) and store it |
| FR3 | System computes engineered features and calls the ML model for probability + risk score + risk level |
| FR4 | System applies a decision engine (Allow / Monitor / Flag / Critical Alert) |
| FR5 | Flagged/critical transactions generate an alert record |
| FR6 | Dashboard shows live KPIs, charts, and tables; updates instantly via WebSocket |
| FR7 | Admin can open a transaction, see explanation, mark reviewed/false-positive/escalate/resolve |
| FR8 | System logs all admin actions to an audit trail |
| FR9 | System can export a CSV report of transactions/alerts |
| FR10 | System displays current model version, training date, and metrics |

**Status: all 10 implemented** — see `backend/app/routes/` for FR1–FR9, `GET /dashboard/model-info` for FR10.

## 6. Non-Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| NFR1 | API prediction latency < 300ms (academic target) | Met — measured ~10-30ms locally (see `docs/test_report.md`) |
| NFR2 | Dashboard update latency after alert creation < 2s (WebSocket) | Met — same-process Socket.IO emit, sub-second |
| NFR3 | Passwords hashed (bcrypt), JWT-based auth, HTTPS in deployment | Met (HTTPS enforced by hosting platform) |
| NFR4 | Handle ≥ 50 concurrent simulated transactions/min | Met — see `docs/testing_strategy.md` load note |
| NFR5 | Code organized as a modular monolith (not literal microservices) | Met — single FastAPI app, layered by module |
| NFR6 | All sensitive config via environment variables, never hardcoded | Met — `app/config/settings.py` + `.env` |

## 7. Users and Roles
- **Admin** — full access: manage users, review/resolve alerts, view all data.
- **Analyst** — can investigate transactions and alerts, cannot manage users.
- **User (viewer)** — read-only dashboard access, for demonstration purposes.
