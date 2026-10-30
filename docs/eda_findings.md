# EDA Findings Summary (Week 2)

Full analysis: `ml/notebooks/01_eda.ipynb` and `ml/notebooks/02_eda_deep.ipynb` (executed, with saved output
cells). Plot: `screenshots/eda/amount_and_hour_distribution.png`.

## Key findings

1. **Severe class imbalance.** 204 of 120,000 transactions are fraud (0.17%) — confirms accuracy alone would
   be a meaningless metric (see `ml/src/train.py` and PART 10.6-style discussion in `docs/model_selection.md`).
2. **Amount distribution is heavily right-skewed** (log-normal shape) for both classes; fraud amounts skew
   slightly higher on average with more variance than legitimate amounts, consistent with the generator's
   design (`ml/src/generate_dataset.py`).
3. **No missing values, no duplicate rows** in the generated dataset (verified programmatically in
   `02_eda_deep.ipynb`).
4. **Outliers.** IQR-based outlier detection on `Amount` flags a small percentage of legitimately-large
   transactions — expected given the log-normal shape, not a data-quality problem.
5. **`V1`-`V28` are anonymized** — correlation with `Class` exists on a specific subset of components (by
   construction; see the generator's `signal_components`), but individual columns are not human-interpretable.
   This is the reason richer, human-readable feature engineering is deferred to the **synthetic live-simulator
   schema** (`docs/feature_plan.md`), not attempted on the Kaggle-schema columns directly.
6. **Time-of-day patterns**: `Time` is seconds-from-first-transaction; converted to `hour_of_day` for pattern
   analysis (see notebook cell 2).

## Conclusion

The dataset is clean, appropriately imbalanced for a realistic fraud-detection exercise, and behaves exactly as
its real-world counterpart (ULB Credit Card Fraud dataset) would in terms of the modeling challenges it poses
(imbalance handling, PR-AUC over ROC-AUC, no shortcut via raw accuracy).
