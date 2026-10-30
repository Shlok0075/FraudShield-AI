# Troubleshooting Guide (PART 22)

## Python
**`ModuleNotFoundError`** — venv not activated, or package not installed in the active venv.
→ `source backend/venv/bin/activate` (or `source ml/venv/bin/activate`), then `pip install <package>`.

**`pip install` fails with permission errors** — trying to install globally instead of inside a venv.
→ Ensure the venv is activated (prompt shows `(venv)`) before `pip install`.

**`email-validator is not installed`** — Pydantic's `EmailStr` needs the optional `email-validator` package.
→ `pip install email-validator` (already pinned in `backend/requirements.txt`).

## FastAPI
**"Address already in use" on `uvicorn` start** — another process is already bound to port 8000.
→ Stop the other process, or `uvicorn app.main:app --port 8001`.

**CORS errors in the browser console** — frontend origin not in the backend's CORS allow-list.
→ Add the exact origin (e.g. `http://localhost:5173`) to `CORS_ORIGINS` in `.env`.

## PostgreSQL
**"connection refused"** — PostgreSQL service not running.
→ `sudo service postgresql start` (Linux) / `brew services start postgresql` (Mac) / Windows services panel.

**"password authentication failed"** — wrong password in `DATABASE_URL`, or user doesn't exist.
→ Reset via `psql`/pgAdmin, update `.env`.

**"database does not exist"** — DB not created yet.
→ `sudo -u postgres psql -c "CREATE DATABASE fraudshield;"`, then `alembic upgrade head`.

## React / Vite
**npm install errors / peer dependency conflicts** — version mismatches.
→ `npm install --legacy-peer-deps` as a fallback.

**API calls fail with network error** — wrong `VITE_API_URL`, or backend not running.
→ Confirm the backend is running and `.env` has the correct base URL.

## WebSockets
**Connection fails** — CORS misconfiguration, or wrong protocol (`ws://` vs `wss://`) in production.
→ Match protocol to the deployment's HTTPS status; confirm CORS allow-list includes the frontend origin.

**Frequent disconnect/reconnect loops** — hosting platform's proxy timing out idle connections.
→ `socket.io-client`'s built-in ping/reconnection (default) handles most cases; check the platform's
WebSocket idle-timeout docs otherwise.

## ML
**Feature mismatch error at prediction time** — the feature vector built by the backend doesn't match the
exact column order/names the model was trained on.
→ The exact feature list is saved in `ml/models/metadata.json['feature_columns']`; `ml/src/predict.py` always
builds the vector in that order via `preprocessing.FEATURE_COLUMNS`.

**Poor model performance live vs. notebook** — feature engineering computed differently live (e.g. missing
transaction history for a brand-new synthetic user).
→ Explicit, documented cold-start defaults in `app/services/feature_engineering.py` (mean=0/std=1 for a
new user, "a long time ago" for time-since-last, etc.) — see also `docs/feature_plan.md`'s "risk-intensity"
note explaining why live scores differ somewhat from the offline-evaluated metrics.

**Model produces perfect (100%) offline metrics** — the synthetic dataset generator's fraud/legit separation
was too easy at first (this actually happened during this project's build — see `ml/src/generate_dataset.py`'s
comments about deliberately overlapping the two classes). If you regenerate the dataset with a different
`random_state` and see suspiciously perfect metrics again, check `FRAUD_RATIO`/the shift magnitudes in
`generate_dataset.py` — real fraud detection is never perfectly separable.

## Deployment
**Environment variable not picked up** — not set in the hosting platform's dashboard, or app reads it with a
different name than expected.
→ Double-check variable names match `backend/.env.example`/`frontend/.env.example` exactly; redeploy after
setting. Never expose actual secret values in a debug endpoint.

## Demo day
**A "suspicious" simulator scenario doesn't score HIGH/CRITICAL on the first try** — this model has a real,
honest recall of ~32% (see `docs/model_selection.md`) — it is *expected* to miss some fraud, exactly like a
real fraud model would. Run `scripts/simulator.py` a few times before the live demo to capture a good example,
or use the "suspicious" scenario (new device + high amount + new location), which reliably scores CRITICAL in
this repo's testing (see `docs/feature_plan.md`'s verified outcome).
