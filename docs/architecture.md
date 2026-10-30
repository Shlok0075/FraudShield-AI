# System Architecture

## 1. High-Level Component Diagram

```
                 +------------------+
                 |   Web Dashboard  |   (React/Vite + Tailwind)
                 +--------+---------+
                          |  HTTPS / WebSocket
                          v
                 +------------------+
                 |    FastAPI       |   (Auth, Transactions, Prediction,
                 |     Backend      |    Alerts, Dashboard, Reports, Audit)
                 +--------+---------+
                          |
             +------------+------------+
             v            v            v
        PostgreSQL     ML Model     Alert Engine
        (SQLAlchemy)  (joblib load) (in-process)
             |            |            |
             +------------+------------+
                          v
                    WebSocket Broadcast
                          |
                          v
                    Live Dashboard Update
```

Three-tier modular monolith: the ML model lives **inside** the FastAPI process (loaded once at startup via
`ModelService.load()`), no separate microservice needed for an academic prototype (NFR5).

## 2. Full Transaction-to-Dashboard Flow

1. Transaction source (simulator or `POST /transactions/predict`)
2. Pydantic validation (`TransactionCreate` schema — amount > 0, required fields present)
3. Feature engineering (`app/services/feature_engineering.py` — velocity, device/location change)
4. ML prediction (`ModelService.predict()` → `ml/src/predict.py`, model loaded once at startup)
5. Risk scoring (`ml/src/decision_engine.py` — probability → risk_score → risk_level)
6. Decision engine (Allow / Monitor / Flag / Critical Alert)
7. Persist `transactions` + `fraud_predictions` rows
8. If `risk_level >= MEDIUM` → create a `fraud_alerts` row
9. Alert Engine emits `new_alert` / `new_transaction` over Socket.IO
10. Connected dashboard clients update React state → re-render (no polling)
11. Admin opens Transaction Detail → reviews SHAP-style explanation → takes action
12. Action written to `audit_logs`

## 3. Authentication Flow

User submits email+password → backend verifies bcrypt hash → issues a JWT (60 min, HS256) → frontend keeps the
token **in memory** (not `localStorage`, to reduce XSS risk — session is lost on refresh, a documented tradeoff,
see Week 9 Day 7) → every request sends `Authorization: Bearer <token>` → backend middleware/dependency decodes
the JWT and checks role against the route's requirement.

## 4. Role Flow Differences

| Role | Access |
|---|---|
| Admin | All routes, including user management and alert resolution |
| Analyst | Transaction/alert investigation routes, cannot manage users |
| User | GET-only dashboard routes |

## 5. Reporting Flow

Admin requests `/reports/export` → backend queries filtered transactions/predictions → Pandas builds a
DataFrame → exported as CSV → returned as a streamed file download.

## 6. Audit Flow

Every state-changing admin action (login, alert status change, transaction action, user create/delete) →
`app/services/audit_service.log_action()` writes a row to `audit_logs` with `user_id`, `action`, `target`,
`timestamp`, `ip_address`.

## 7. Real Component Map (this repo)

| Diagram box | Actual code |
|---|---|
| Web Dashboard | `frontend/src/` (React + Vite + Tailwind + Recharts) |
| FastAPI Backend | `backend/app/main.py` + `app/routes/*.py` |
| PostgreSQL | `backend/app/models/*.py` (SQLAlchemy) + `backend/alembic/` |
| ML Model | `ml/src/predict.py`, wrapped by `backend/app/ml/model_service.py` |
| Alert Engine | `backend/app/websocket/socket_server.py` |
