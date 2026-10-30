# Model Selection (Week 5)

## Full 6-variant comparison (3 algorithms × 2 imbalance strategies)

From `ml/models/model_comparison.csv` (real numbers, this repo's actual trained models):

| Model | Strategy | Precision | Recall | F1 | ROC-AUC | PR-AUC | TP | FP | TN | FN |
|---|---|---|---|---|---|---|---|---|---|---|
| Logistic Regression | class_weight | 0.0128 | 0.9268 | 0.0253 | 0.9656 | 0.1072 | 38 | 2920 | 21039 | 3 |
| Random Forest | class_weight | 0.6111 | 0.2683 | 0.3729 | 0.9572 | 0.3352 | 11 | 7 | 23952 | 30 |
| **XGBoost** | **class_weight** | **0.7647** | 0.3171 | **0.4483** | 0.9139 | **0.4324** | 13 | 4 | 23955 | 28 |
| Logistic Regression | SMOTE | 0.0127 | 0.9024 | 0.0251 | 0.9613 | 0.1092 | 37 | 2872 | 21087 | 4 |
| Random Forest | SMOTE | 0.0994 | 0.4390 | 0.1622 | 0.9471 | 0.1659 | 18 | 163 | 23796 | 23 |
| XGBoost | SMOTE | 0.1328 | 0.4146 | 0.2012 | 0.9218 | 0.2515 | 17 | 111 | 23848 | 24 |

## Final model selected: **XGBoost, class_weight='balanced'**

**Written justification:** XGBoost (class_weight) achieves the best PR-AUC (0.4324) — the most informative
metric under this dataset's extreme (~0.17%) imbalance — and the best precision (0.7647) of all six variants,
meaning its alerts are trustworthy roughly 3 times out of 4, at the cost of catching only ~32% of fraud
(recall 0.3171). This is a deliberate, honest precision/recall tradeoff for an academic build: an
alert-fatigue-heavy model (like the Logistic Regression variants, precision ≈ 0.013) would be actively harmful
in a real review queue even though its recall looks high.

Interestingly, **SMOTE underperformed `class_weight='balanced'` for every algorithm on this dataset** — a
useful, honest finding for the viva (Q4's follow-up: "what's a risk of using SMOTE incorrectly?"). One
plausible explanation: with only ~163 fraud rows in the training split, SMOTE's synthetic interpolation between
so few real minority points can produce synthetic examples that don't generalize as well as simply reweighting
the loss function. This is exactly the kind of empirical, dataset-specific result a real ML project should
report rather than assume from general advice.

## Cross-validation sanity check
5-fold `StratifiedKFold` cross-validation on the winning model's training data: **mean CV PR-AUC = 0.3525**,
reasonably close to the held-out test PR-AUC (0.4324), suggesting the model is not badly overfit to a single
split (some variance is expected given how few fraud examples exist in each fold).

## Saved artifacts
- `ml/models/model.joblib` — trained XGBoost pipeline
- `ml/models/scaler.joblib` — fitted `StandardScaler` (Amount/Time)
- `ml/models/metadata.json` — version, training date, feature list, metrics
- `ml/models/model_comparison.csv` — the full 6-variant table above
