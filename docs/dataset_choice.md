# Dataset Choice — Week 1, Day 4

## Candidates evaluated

| Dataset | Pros | Cons |
|---|---|---|
| **Credit Card Fraud Detection (ULB/Kaggle)** | ~284,807 real transactions, 492 fraud (~0.172%), clean, extremely well-known, easy to defend in a viva | Features `V1`–`V28` are PCA-anonymized — not human-readable, limits feature-engineering scope |
| **IEEE-CIS Fraud Detection (Kaggle)** | Much richer raw feature set (device, card, email domain) | Larger, messier, harder to fully clean and explain in a 4-month solo project |
| **Synthetic transaction generator** | Fully controllable, every feature explainable, ideal for a live real-time demo | Not "real" data on its own — needs to be paired with something recognizable |

## Decision

**Primary training dataset for the live model: PaySim**
(`PS_20174392719_1491204439457_log.csv`, Lopez-Rojas et al., Kaggle 'ealaxi/paysim1'), 6,362,620 rows,
8,213 fraud (0.1291%). The live hybrid model (`ml/models/live-v1/`) is trained on PaySim point-in-time
features (`ml/data/processed/paysim-v1/`), with XGBoost + IsolationForest + behavior + rules combined
through a validation-tuned risk engine.

The Credit Card Fraud Detection schema (`Time`, `V1`–`V28`, `Amount`, `Class`) is maintained as a
**legacy/offline benchmark** (`ml/data/raw/creditcard.csv`, 120,000 rows, 204 fraud, 0.17%) generated
synthetically by `ml/src/generate_dataset.py`. The legacy model (`ml/models/model.joblib`) remains
available but is not the active serving model.

This is combined, in Month 3, with our **own synthetic transaction simulator** (`scripts/simulator.py`) that
generates human-readable, richly engineered features (velocity, device change, location change) for the live
real-time dashboard demo — see `docs/feature_plan.md`.

## Explicit limitation (see PART 21, Q25)

This combination is **not representative of real-world fraud patterns today**. It is an academic approximation
used to demonstrate the ML → API → real-time dashboard pipeline end-to-end, not a deployable banking system.

## Where the data lives

- `ml/src/generate_dataset.py` — legacy credit-card generator (deterministic via `random_state=42`)
- `ml/data/raw/creditcard.csv` — legacy generated dataset (120,000 rows, 204 fraud, 0.17%)
- `ml/data/raw/PS_20174392719_1491204439457_log.csv` — PaySim raw (6,362,620 rows; 493 MB, not shipped)
- `ml/data/processed/paysim-v1/` — PaySim point-in-time features, train/val/test split
- `ml/models/live-v1/` — active serving model trained on PaySim 6M
- `ml/models/model.joblib` — legacy credit-card model (not active)
