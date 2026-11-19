# 🛡️ FraudShield AI

**Intelligent Online Transaction Fraud Detection and Real-Time Monitoring System**
B.Tech Final Year Project — Academic Prototype, built end-to-end following the *FraudShield AI 4-Month
Complete Project Development Handbook*.

> **Academic disclaimer:** this is an ACADEMIC PROTOTYPE, not a production banking system. It uses
> public/synthetic datasets and simulated transactions only. Never use real card numbers, CVVs, OTPs, or real
> banking credentials anywhere in this project.

## What this is

A web-based platform that ingests transaction data, scores each transaction for fraud risk using a trained
Machine Learning model (XGBoost), and surfaces suspicious activity to an administrator through a real-time
dashboard — combining applied ML, backend/API engineering, and real-time web development.

Every part of this project was actually built and verified running end-to-end during development: real trained
model artifacts, a real PostgreSQL database with Alembic migrations, a live FastAPI backend, a live React
dashboard tested with a real browser, 108 passing automated tests (56 backend, 52 ML), and full documentation. See `docs/` for the
complete handbook-structured write-up (architecture, security, testing, deployment, final report, viva prep).

## Technology Stack

| Layer | Stack |
|---|---|
| Frontend | React (Vite) + Tailwind CSS v4 + Recharts + Axios + socket.io-client |
| Backend | Python 3.11 + FastAPI + Uvicorn + SQLAlchemy + Alembic + python-socketio + slowapi |
| ML | pandas, NumPy, scikit-learn, XGBoost, imbalanced-learn (SMOTE), SHAP, joblib |
| Database | PostgreSQL 16 |
| Auth | JWT (python-jose) + bcrypt (passlib) + RBAC |
| Deployment | Docker Compose (local) / Vercel + Render/Railway + managed Postgres (hosted) |

## Project Structure

```
FraudShield-AI/
├── frontend/        React dashboard (Login, Dashboard, Alerts, Transaction Detail, Audit Log, Users)
├── backend/         FastAPI app (auth, transactions, predict, alerts, dashboard, reports, audit)
│   ├── app/         models, schemas, routes, services, ml wrapper, auth, websocket
│   ├── alembic/     database migrations
│   └── tests/       pytest unit + integration tests (56 tests)
├── ml/
│   ├── notebooks/   01_eda → 05_tuning, executed with saved output cells
│   ├── src/         generate_dataset, preprocessing, train, predict, decision_engine (+18 tests)
│   └── models/      model.joblib, scaler.joblib, metadata.json, model_comparison.csv
├── scripts/         simulator.py — 6-scenario synthetic transaction generator
├── docs/            full handbook documentation (23 files — architecture through viva prep)
├── screenshots/     EDA plots
└── docker-compose.yml
```

## Quickstart (local)

### 1. Database
```bash
sudo service postgresql start
sudo -u postgres psql -c "CREATE DATABASE fraudshield;"
```

### 2. Train the ML model
```bash
cd ml
python3 -m venv venv && source venv/bin/activate    # or reuse backend/venv
pip install -r requirements.txt
python src/generate_dataset.py    # writes ml/data/raw/creditcard.csv (synthetic, ~120k rows)
python src/train.py               # trains 6 model variants, saves the best to ml/models/
```
*(Already done in this delivered copy — `ml/models/` ships with real trained artifacts. Re-run only if you
want to regenerate them, e.g. with a real `creditcard.csv` from Kaggle dropped into `ml/data/raw/`.)*

### 3. Backend
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env    # edit DATABASE_URL / JWT_SECRET as needed
alembic upgrade head
uvicorn app.main:app --reload
```
Swagger UI: http://localhost:8000/docs · Health check: http://localhost:8000/health

### 4. Frontend
```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```
Open http://localhost:5173, register an admin (`POST /api/v1/auth/register` via Swagger, or just try logging in
— the app will prompt registration failure clearly) and log in.

### 5. Live simulator (optional, for the real-time demo)
```bash
python scripts/simulator.py --base-url http://localhost:8000 --interval 2
```
Watch the dashboard's "Live Feed" panel update instantly via WebSocket as transactions are scored.

### One-command alternative: Docker Compose
```bash
docker compose up --build
```

## Tests

```bash
cd backend && source venv/bin/activate && pytest tests/ --cov=app        # 56 tests
cd ml/src && pytest test_ml.py test_pipeline.py test_risk_engine.py test_experiments.py   # 52 tests
```

## Model performance (real numbers, this repo)

Serving model (`ml/models/live-v1`, `live-hybrid-v1`): XGBoost risk score, trained on PaySim 6M
(6,362,620 rows, 8,213 fraud) with a chronological split and leakage-safe point-in-time features. Test metrics on the
held-out 1,293,523-row split (4,258 fraud), thresholds chosen on validation:

| | PR-AUC | ROC-AUC | Review (recall / precision) | Block (recall / precision) |
|---|---|---|---|---|
| Before bug fix | 0.3255 | 0.8915 | 0.959 / 0.0045 | 0.075 / 0.936 |
| **Now** | **0.5147** | **0.9666** | 0.931 / 0.015 | 0.625 / 0.254 |

The earlier numbers were low because the transaction type never reached the model (see `docs/paysim_evaluation.md`).
The blend weights are now selected with a parsimony guard, which picked ML-only: PaySim users almost never repeat
(99.7% of test transactions are a user's first), so behaviour and rule signals add nothing there.
This is a *realistic, no-balance-features* benchmark; PaySim balance columns are deliberately excluded by default
(`build_dataset --balance` adds them back as an optional feature group). Metrics are on synthetic PaySim data, not
production banking performance.
Full experiment results in `ml/models/live-v1/metadata.json` and `ml/data/processed/paysim-v1/`.

## Documentation index (`docs/`)

`requirements.md` · `architecture.md` · `dataset_choice.md` · `data_dictionary.md` · `eda_findings.md` ·
`data_leakage_notes.md` · `feature_plan.md` · `month1_summary.md` · `model_selection.md` · `risk_scoring.md` ·
`realtime_flow.md` · `security.md` · `testing_strategy.md` · `test_report.md` · `model_monitoring.md` ·
`deployment.md` · `uml_diagrams.md` · `postman_collection.json` · `final_report.md` ·
`presentation_outline.md` · `demo_script.md` · `viva_prep.md` · `troubleshooting.md` · `final_checklist.md`

## License

See `LICENSE`.

## Public-dataset experiment (PaySim)

The project's planned public-dataset evaluation uses the Kaggle **PaySim** dataset
(`PS_20174392719_1491204439457_log.csv`, Lopez-Rojas et al.). It is intentionally
not shipped (493 MB) — download it once and place it in `ml/data/raw/`:

```bash
# Option A: Kaggle CLI (needs a Kaggle API token)
kaggle datasets download -ealaxi/paysim1 -p ml/data/raw --unzip

# Option B: direct mirror
curl -L -o ml/data/raw/PS_20174392719_1491204439457_log.csv \
  https://huggingface.co/datasets/vitaliy-sharandin/synthetic-fraud-detection/resolve/main/PS_20174392719_1491204439457_log.csv
```

Then run the full public-dataset pipeline (builds point-in-time features, time-aware
split, trains 6 model variants + Isolation Forest, selects thresholds on validation,
evaluates test once):

```bash
cd ml/src
python -m fraudpipe.build_dataset --input ../data/raw/PS_20174392719_1491204439457_log.csv \
    --out ../data/processed/paysim-v1 --seed 42
python -m fraudpipe.experiments --data ../data/processed/paysim-v1 \
    --out ../models/experiments/paysim-v1 --seed 42
```

Results land in `ml/models/experiments/paysim-v1/model_comparison.csv` and
`experiment_results.json` (PR-AUC, ROC-AUC, precision, recall, F1, FPR, FNR per model).
These are **public-dataset** metrics and are kept separate from the synthetic
benchmark in `docs/final_checklist.md`.

## Behavioral Hybrid Model (Phase 6)

The live transaction path now uses the shared point-in-time `FeatureEngine` instead of the legacy V1–V28 risk-intensity projection. It combines XGBoost, Isolation Forest, behavioral scoring and deterministic fraud rules through a validation-tuned risk engine. See `docs/hybrid_integration.md`.

## Major-project upgrade modules

The current build includes a shared point-in-time behavioral feature engine and a hybrid fraud risk path:

`Transaction -> FeatureEngine -> XGBoost + Isolation Forest + Behavioral Score + Rules -> Risk Aggregator -> Alert/Case`

Additional major-project modules now included:

- investigation case management and analyst notes
- confirmed-fraud / false-positive feedback capture
- feedback retraining manifest generation
- user behavioral profiles
- merchant risk analytics
- model registry and activation metadata
- prediction-distribution drift monitoring (PSI)
- graph relationship risk endpoint (User/Device/Merchant)
- security-control test matrix endpoint
- expanded transaction simulator scenarios

The project remains an academic prototype. Public/synthetic data and simulated transactions do not establish production banking performance.
