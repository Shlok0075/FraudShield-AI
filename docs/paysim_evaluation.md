# Public-Dataset Evaluation — PaySim (PART 21)

## Dataset

- **Source:** PaySim (Lopez-Rojas et al., Kaggle `ealaxi/paysim1`) — `PS_20174392719_1491204439457_log.csv`
- **SHA-256:** `16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b`
- **Rows:** 6,362,620 | **Fraud:** 8,213 (0.129%)
- **Dropped columns:** `oldbalanceOrg`, `newbalanceOrig`, `oldbalanceDest`, `newbalanceDest`, `isFlaggedFraud`
  (post-transaction balances are derived from the fraud label; `isFlaggedFraud` is a rule-system output, not ground truth.)

## Feature contract

Point-in-time behavioral features from `fraudpipe.features.FeatureEngine` (groups = `core`,
label_delay_s = 86400). The SAME engine is used for offline training and live inference, so the
offline benchmark is directly comparable to the production prediction path.

## Split (time-aware, never random)

| Split   | Rows    | Fraud | Fraud rate |
|---------|---------|-------|------------|
| train   | 3,792,821 | 3,175 | 0.0837% |
| val     | 1,276,276 | 780   | 0.0612% |
| test    | 1,293,523 | 4,258 | 0.3292% |

Cut-offs are on timestamp quantiles; no timestamp is shared between splits.

## Protocol

1. Fit preprocessing on **train only**; apply to val/test.
2. Fit each model on train.
3. **Select thresholds on validation** (`fraudpipe.metrics.select_thresholds`).
4. Evaluate test **once**, at the validation-selected thresholds.

## Results (test set, thresholds from validation)

| Model                        | PR-AUC  | ROC-AUC | Precision | Recall | F1     | FPR     | FNR     |
|------------------------------|---------|---------|-----------|--------|--------|---------|---------|
| XGBoost + class_weight       | 0.5203  | 0.9665  | 0.2515    | 0.6322 | 0.3598 | 0.0062  | 0.3678  |
| XGBoost + SMOTE              | 0.4990  | 0.9710  | 0.5091    | 0.4476 | 0.4764 | 0.0014  | 0.5524  |
| Random Forest + class_weight | 0.4583  | 0.9696  | 0.5596    | 0.4089 | 0.4725 | 0.0011  | 0.5911  |
| Random Forest                | 0.4375  | 0.9609  | 0.4517    | 0.4735 | 0.4623 | 0.0019  | 0.5265  |
| XGBoost                      | 0.3056  | 0.9706  | 0.4441    | 0.3217 | 0.3731 | 0.0013  | 0.6783  |
| Logistic Regression          | 0.2320  | 0.9024  | 0.7133    | 0.1221 | 0.2085 | 0.0002  | 0.8779  |
| LogReg + class_weight        | 0.1292  | 0.9381  | 0.0989    | 0.4274 | 0.1607 | 0.0129  | 0.5726  |
| Isolation Forest (unsup.)    | 0.0319  | 0.8676  | 0.0722    | 0.1235 | 0.0911 | 0.0052  | 0.8765  |

Best PR-AUC on PaySim: **XGBoost + class_weight (0.5203)**, at the balanced threshold (0.95) selected on
validation. The tuned hybrid risk engine used by the live API is a separate artifact
(`ml/models/live-v1/`) trained on the synthetic behavioral stream — it is **not** re-tuned on PaySim.

## Reproducibility

```bash
cd ml/src
python -m fraudpipe.build_dataset --input ../data/raw/PS_20174392719_1491204439457_log.csv \
    --out ../data/processed/paysim-v1 --seed 42
python -m fraudpipe.experiments --data ../data/processed/paysim-v1 \
    --out ../models/experiments/paysim-v1 --seed 42
```

Artifacts: `ml/models/experiments/paysim-v1/{experiment_results.json,model_comparison.csv}`.

## Honest limitations

- PaySim is itself a **synthetic** simulator, not real transaction data. Metrics above are an
  academic demonstration of the evaluation pipeline, not production banking performance.
- Fraud rate is ~0.13% and the test split is chronologically later than train/val, so the test
  fraud rate (0.33%) is higher than train (0.08%) — the model is evaluated on a genuinely harder,
  later window.
- These numbers are **public-dataset** results and are reported separately from the synthetic
  behavioral benchmark in `docs/final_checklist.md`. Neither is a substitute for the other.