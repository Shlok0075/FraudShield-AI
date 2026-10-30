# Data Dictionary

## Kaggle-schema dataset (`ml/data/raw/creditcard.csv`)

| Column | Type | Description | Example | Notes |
|---|---|---|---|---|
| `Time` | float | Seconds elapsed since the first transaction in the dataset | 4462.0 | Used to derive hour-of-day patterns |
| `Amount` | float | Transaction amount | 149.62 | Core fraud signal — unusual amounts raise risk |
| `V1`..`V28` | float | PCA-anonymized features | -1.359807 | Not individually human-interpretable; SHAP still ranks their contribution |
| `Class` | int (0/1) | Target label, 1 = fraud, 0 = legitimate | 0 | ~0.17% positive class |

Computed on the actual generated dataset (120,000 rows):
- Fraud count: **204** (0.1700%)
- Missing values: **0**
- Duplicate rows: **0** (see `ml/notebooks/02_eda_deep.ipynb`)

## Synthetic live-simulator schema (`scripts/simulator.py` → `POST /transactions/predict`)

| Field | Type | Description |
|---|---|---|
| `user_id` | int | Synthetic actor id (not an auth account — see `backend/app/models/transaction.py` docstring) |
| `amount` | float | Transaction amount, > 0 |
| `merchant_id` | int, optional | FK to `merchants` |
| `device_id` | string | Synthetic device fingerprint |
| `location` | string, optional | Free-text location label |
| `ip_address` | string, optional | Synthetic IP |
| `payment_method` | string, optional | e.g. "card" |

Derived features (computed live by `app/services/feature_engineering.py`):

| Derived field | Description |
|---|---|
| `amount_zscore` | How unusual this amount is vs. the user's own transaction history |
| `txn_count_last_5min` | Velocity signal — rapid repeated transactions |
| `time_since_last_txn_sec` | Very short gaps are suspicious |
| `new_device_flag` | 1 if this device has never been seen for this user |
| `location_change_flag` | 1 if location differs from the user's last known location |
| `user_historical_fraud_rate` | Proportion of this user's past HIGH/CRITICAL predictions |

These are explicitly labeled SYNTHETIC/SIMULATED, computed live from our own database tables
(`devices`, `transactions`), **not** derived from the Kaggle-schema dataset.
