# Deployment Guide (Week 15)

## What was verified in this environment (documented as the local fallback, PART 16 step 9)

This project was fully exercised **locally** end-to-end during development, standing in for a hosted demo:

1. **PostgreSQL 16** running locally (`pg_ctlcluster` / `service postgresql start`), database `fraudshield` created.
2. **Alembic migrations** generated (`alembic revision --autogenerate`) and applied (`alembic upgrade head`) —
   all 8 tables (`users`, `merchants`, `devices`, `transactions`, `fraud_predictions`, `fraud_alerts`,
   `audit_logs`, `model_versions`) created from the SQLAlchemy models, not by hand.
3. **Backend** (`uvicorn app.main:app`) started against that real Postgres instance; `/health` returned
   `{"status": "ok"}` publicly on the container's port 8000.
4. **Frontend** (`npm run dev`) started against `VITE_API_URL=http://localhost:8000`; login, dashboard, alerts,
   and transaction-detail pages all verified against the live backend with real data (screenshots captured).
5. **WebSocket connectivity** verified: `new_transaction`/`new_alert` events observed live-updating the
   dashboard's "Live Feed" panel while `scripts/simulator.py` ran.
6. **Full docker-compose stack** (`docker-compose.yml`) provided as the reproducible one-command fallback for
   viva day — see below.

## Suggested low-cost hosted deployment (as designed, PART 2)

| Component | Platform | Notes |
|---|---|---|
| Frontend | Vercel | Free tier, auto-deploy from GitHub, set `VITE_API_URL` env var to the backend URL |
| Backend | Render / Railway | Free/low-cost tier, supports FastAPI + WebSockets; set `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS` in the platform dashboard, never in code |
| Database | Render / Neon / Supabase managed PostgreSQL | Free tier |
| ML model | Bundled inside the backend service | No separate hosting needed |

### Steps
1. Deploy PostgreSQL (managed free tier); note its connection string.
2. Run `alembic upgrade head` against it (from a machine with the `.env` pointed at the managed DB).
3. Deploy the backend; set `DATABASE_URL`, `JWT_SECRET`, `CORS_ORIGINS` in the platform's dashboard.
4. Deploy the frontend; set `VITE_API_URL` to the deployed backend's URL.
5. Verify WebSocket connectivity over HTTPS/WSS (a common failure point — check the platform's WebSocket/proxy
   docs if the socket fails to connect; `wss://` is required once the site is served over HTTPS).
6. Run `scripts/simulator.py --base-url https://<your-backend>` against the deployed backend to confirm the
   live dashboard updates in production, not just locally.

## Local Docker Compose fallback

```bash
docker compose up --build
```
Brings up Postgres, the backend (with migrations applied automatically on startup via the app's lifespan hook),
and can be extended with an `frontend` service (`Dockerfile` provided) — see `docker-compose.yml` at the repo
root.
