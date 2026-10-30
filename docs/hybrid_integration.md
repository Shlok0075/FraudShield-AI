# FraudShield AI — Phase 6 Backend Integration

## What changed

The live `/api/v1/transactions/predict` path no longer projects behavioral signals onto anonymized `V1–V28` columns.
It now uses the shared `ml/src/fraudpipe/FeatureEngine` for point-in-time behavioral features and the `live-v1` model bundle.

### Live pipeline

```text
Incoming transaction
        ↓
Point-in-time FeatureEngine
        ↓
XGBoost fraud probability ─┐
Isolation Forest score ────┤
Behavior score ────────────┤→ Hybrid Risk Engine → 0–100 score
Deterministic rules ──────┘                    → ALLOW/REVIEW/BLOCK
                                                ↓
                                          Explanation + Alert
```

## Leakage protection

Feature computation happens **before** the current transaction and new device are persisted. Historical rows are replayed in timestamp/order sequence, so the current transaction cannot affect its own features.

The feature engine supports a 24-hour label maturation delay. The current legacy database has no analyst-confirmed label table yet, so live prior-fraud-rate features remain at the configured prior until the feedback/case phase is implemented.

## Live model

`ml/models/live-v1/` contains:

- `supervised.joblib` — XGBoost classifier
- `isolation_forest.joblib` — anomaly detector
- `preprocessor.json` — feature schema and training medians
- `risk_config.json` — validation-tuned hybrid weights/thresholds
- `metadata.json` — dataset, split, metrics and provenance

The training data are **synthetic behavioral stream data**, not a real banking dataset. The model is therefore an academic demonstration artifact, not evidence of production fraud performance.

## Re-training

```bash
cd ml/src
python train_live_model.py
```

This regenerates the synthetic behavioral dataset, builds point-in-time features, trains XGBoost + Isolation Forest, tunes the hybrid weights on validation data, and writes the live model bundle.

## Current benchmark

The bundled synthetic live model was trained on 60,000 rows with a 60/20/20 chronological split. Test PR-AUC is approximately 0.604 and ROC-AUC approximately 0.939. Review and block thresholds are selected on validation data. These numbers must not be presented as real-world banking performance.

The tuner selected 0.90 ML weight and 0.10 behavior weight on this synthetic fixture; anomaly and rule weights were zero because they did not improve validation PR-AUC under the tuning protocol. The runtime engine still computes all four signals and returns them. When a real behavioral dataset is introduced, the weights must be re-tuned and reported rather than manually forced.

## Backward compatibility

The response keeps the previous human-facing `decision` values (`Allow`, `Monitor`, `Critical Alert`) and adds `hybrid_decision` with normalized `ALLOW`, `REVIEW`, and `BLOCK` values, plus individual signal scores, triggered rules, readable reasons, and signal contributions.

## Production-scale limitation

For this academic implementation, the backend replays database history during prediction. This prioritizes correctness and restart safety. A production architecture should replace this with a persistent/streaming feature store or equivalent stateful feature service.
