# Synthetic Feature Plan (Week 4, Day 2) & Live Risk-Intensity Mapping

## Which features are derivable from the Kaggle-schema dataset?

**None directly** — `V1`-`V28` are anonymized/PCA-transformed by the original dataset's publisher for
confidentiality, so there is no way to recover "device changed" or "location changed" style features from them.
Only `Amount` and `Time` are human-readable, and are used for `Amount_scaled`/`Time_scaled` (Week 3).

## Richer features for the live synthetic simulator (Month 3)

Computed live by `backend/app/services/feature_engineering.py` from our own database tables
(`transactions`, `devices`), not from the Kaggle-schema dataset:

| Feature | Derivation |
|---|---|
| `amount_zscore` | `(amount - user_mean_amount) / user_std_amount`, computed over the user's own past transactions |
| `txn_count_last_5min` | count of this user's transactions in the last 5 minutes (velocity) |
| `time_since_last_txn_sec` | seconds since this user's last transaction |
| `new_device_flag` | 1 if `device_id` has never been seen for this `user_id` |
| `location_change_flag` | 1 if `location` differs from the user's most recent transaction's location |
| `user_historical_fraud_rate` | proportion of this user's past predictions at HIGH/CRITICAL |

Cold-start defaults (documented in `feature_engineering.py`): a brand-new synthetic user with no history gets
`mean_amount=0, std_amount=1` (so their first `amount_zscore` is just the raw amount) rather than crashing on
division-by-zero or producing `NaN`.

## Live risk-intensity mapping (why the model reacts to velocity/new-device/location on the live path)

The offline-trained model (`ml/src/train.py`) only ever saw the 30 Kaggle-schema columns (`V1`-`V28`,
`Amount_scaled`, `Time_scaled`). It has no concept of "new device" as a named feature. To let the **same**
trained model meaningfully react to the live synthetic signals without retraining a second model, we:

1. Combine the live synthetic signals into a single `risk_intensity ∈ [0, 1]`:
   ```
   risk_intensity = 0.30·new_device + 0.25·velocity + 0.20·rapid_repeat
                  + 0.15·location_change + 0.10·amount_zscore_component
   ```
2. Project that intensity onto the 8 `V`-columns (`V2, V4, V5, V11, V12, V14, V17, V18`) the offline model
   happens to weight most heavily for the fraud class, in the empirically-determined direction each one moves
   toward "more fraud-like" (found via a small grid search against the trained model — see
   `backend/app/services/feature_engineering.py`'s `_SIGNAL_DIRECTIONS`).

This is a **documented design choice**, not a hidden shortcut: it is the honest way to let one trained model
serve both the offline Kaggle-schema evaluation (`docs/model_selection.md`) and the live demo path, without
pretending the anonymized `V`-columns "mean" velocity or device-change (they don't — they're PCA components).
A real production system would instead train directly on the richer, human-readable schema from day one; that
is out of scope for a 4-month academic build using a public/synthetic PCA-anonymized dataset as the primary
training source.

## Verified outcome (see `docs/test_report.md` and the demo script)

- A **normal** transaction (known device, modest amount) scores LOW.
- A **suspicious** transaction (new device + high amount + new location) reliably scores CRITICAL.
- A **repeat transaction with an already-known device/amount** scores lower over time, matching real user
  profiling behavior.

---

## Phase 6 update — live V1–V28 projection retired

The earlier `risk_intensity` projection onto anonymized V-columns was a prototype bridge and is no longer used by the primary live prediction path. The backend now uses the shared point-in-time `fraudpipe.FeatureEngine` with real behavioral features. The historical notes above are retained as project history; see `docs/hybrid_integration.md` for the current architecture.
