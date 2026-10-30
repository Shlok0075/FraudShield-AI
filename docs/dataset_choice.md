# Dataset Choice — Week 1, Day 4

## Candidates evaluated

| Dataset | Pros | Cons |
|---|---|---|
| **Credit Card Fraud Detection (ULB/Kaggle)** | ~284,807 real transactions, 492 fraud (~0.172%), clean, extremely well-known, easy to defend in a viva | Features `V1`–`V28` are PCA-anonymized — not human-readable, limits feature-engineering scope |
| **IEEE-CIS Fraud Detection (Kaggle)** | Much richer raw feature set (device, card, email domain) | Larger, messier, harder to fully clean and explain in a 4-month solo project |
| **Synthetic transaction generator** | Fully controllable, every feature explainable, ideal for a live real-time demo | Not "real" data on its own — needs to be paired with something recognizable |

## Decision

**Primary dataset: Credit Card Fraud Detection schema (`Time`, `V1`–`V28`, `Amount`, `Class`)**, generated
synthetically by `ml/src/generate_dataset.py` to match the real ULB dataset's exact schema, size class and
imbalance ratio (~0.17% fraud). The original Kaggle CSV requires a Kaggle account/API token and cannot be
redistributed inside this handbook's project zip, so a schema-identical synthetic generator stands in for it —
**anyone with Kaggle access can instead drop the real `creditcard.csv` into `ml/data/raw/` and every downstream
script (`preprocessing.py`, `train.py`, the notebooks) works unchanged**, since only the file's contents differ,
not its shape.

This is combined, in Month 3, with our **own synthetic transaction simulator** (`scripts/simulator.py`) that
generates human-readable, richly engineered features (velocity, device change, location change) for the live
real-time dashboard demo — see `docs/feature_plan.md`.

## Explicit limitation (see PART 21, Q25)

This combination is **not representative of real-world fraud patterns today**. It is an academic approximation
used to demonstrate the ML → API → real-time dashboard pipeline end-to-end, not a deployable banking system.

## Where the data lives

- `ml/src/generate_dataset.py` — generator (documented, deterministic via `random_state=42`)
- `ml/data/raw/creditcard.csv` — generated dataset (120,000 rows, 204 fraud, 0.17%)
- `ml/data/processed/{train,test}.csv` — post-split, post-scaling artifacts (written by `preprocessing.py`)
