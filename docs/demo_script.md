# Demonstration Script (10-15 minutes)

**Setup before demo:** Postgres running, migrations applied (`alembic upgrade head`), backend running
(`uvicorn app.main:app`), frontend running (`npm run dev`), model trained (`python ml/src/train.py`).

**Step 1 — Login as admin.**
> "I'll log in as an administrator to access the full FraudShield AI dashboard."
(Login with `admin@fraudshield.ai` / the password you registered.)

**Step 2 — Show dashboard.**
> "Here you can see live KPIs — total transactions, fraud rate, active alerts — all pulled from our PostgreSQL
> database in real time, along with the currently active model's version and offline metrics."

**Step 3 — Generate a normal transaction.**
> "I'll simulate a normal transaction — reasonable amount, known device."
Run: `python scripts/simulator.py --count 1` with a "normal" scenario, or trigger one manually via the Swagger
UI (`/docs`) on `POST /transactions/predict`.

**Step 4 — Show the prediction result.**
> "The system scored this at a low risk — you can see it was allowed automatically."

**Step 5 — Generate a suspicious transaction (new device + high amount + new location).**
> "Now I'll simulate a suspicious transaction with a new device, an unusually high amount, and a location this
> user has never used before."
This scenario reliably scores **CRITICAL** in this repo's live testing (see `docs/feature_plan.md`).

**Step 6 — Show the ML risk score.**
> "The model immediately assigns a risk score — here it's flagged as CRITICAL risk."

**Step 7 — Show the instant alert appearing on the dashboard (no refresh).**
> "Notice the alert appeared instantly in the Live Feed panel, without refreshing the page — that's our
> WebSocket real-time pipeline."

**Step 8 — Open the transaction investigation page.**
> "As an administrator, I can drill into this transaction for full details."

**Step 9 — Show the explanation panel.**
> "The system explains WHY it was flagged — here, these anonymized pattern signals were the biggest
> contributing factors, using SHAP-based explainability. This is a model-derived statistical indicator, not
> proof of fraud — a human must still review before any real action is taken."

**Step 10 — Show analytics/charts.**
> "Our analytics section shows fraud trends over time, risk distribution, and geographic patterns."

**Step 11 — Show audit logs.**
> "Every administrative action — like marking this as reviewed — is recorded in an audit trail for
> accountability."

**Step 12 — Explain ML model performance.**
> "Our final model, XGBoost, achieved 76.5% precision and 31.7% recall on held-out test data, chosen after
> comparing it against Logistic Regression, Random Forest, and two imbalance-handling strategies —
> class-weighting and SMOTE — across all three algorithms."

**Close:** "That concludes the demonstration — happy to answer any questions."
