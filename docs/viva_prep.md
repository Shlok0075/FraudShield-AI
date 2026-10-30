# Viva Preparation

Format: Question / Short answer / Detailed answer / Possible follow-up. Answers below are filled in with this
project's **actual** numbers, not placeholders.

## General Project

**Q1. What problem does FraudShield AI solve?**
Short: Detecting likely-fraudulent online transactions using ML instead of rigid rules.
Detailed: Rule-based systems are static and easy to bypass; FraudShield learns patterns from historical labeled
data to assign a probabilistic risk score, catching subtler fraud patterns while explaining its reasoning via
SHAP.
Follow-up: How would this differ for a real bank? → Real payment-gateway integration, PCI-DSS compliance,
continuous retraining, and human-reviewed feedback loops feeding back into the training set.

**Q2. Why did you choose fraud detection as your project?**
Combines ML, backend engineering, database design, real-time systems, and security in one practical domain —
demonstrating skills that map directly to industry roles.

## Machine Learning

**Q3. Why is accuracy a poor metric here?**
With a 0.17% fraud rate, a model predicting "never fraud" would score 99.83% accuracy while catching zero
fraud. Precision/Recall/F1/PR-AUC better reflect real detection performance on the rare class.

**Q4. What is class imbalance and how did you handle it?**
Compared `class_weight='balanced'` vs. SMOTE across all three algorithms (`docs/model_selection.md`).
**Actual finding in this project: `class_weight='balanced'` outperformed SMOTE for every algorithm** (e.g.
XGBoost PR-AUC 0.4324 vs. 0.2515) — a good, honest, dataset-specific result to discuss.
Follow-up: risk of using SMOTE incorrectly? → Applying it before the train/test split, or to the test set,
leaks synthetic-but-derived information and inflates reported recall.

**Q5. Why XGBoost over Logistic Regression?**
XGBoost (class_weight) achieved precision 0.7647 / PR-AUC 0.4324 vs. Logistic Regression's precision 0.0128 —
tree ensembles capture non-linear feature interactions linear models cannot.
Follow-up: why not always use the most complex model? → Diminishing returns + interpretability/latency cost;
Random Forest and XGBoost were both compared, not assumed superior.

**Q6. Why not Deep Learning?**
Overkill for ~120,000 rows of tabular data; gradient-boosted trees are competitive and far more interpretable —
appropriate for a 4-month academic scope.

**Q7. What is overfitting and how did you guard against it?**
Guarded via stratified train/test split, 5-fold cross-validation (mean CV PR-AUC 0.3525, close to test PR-AUC
0.4324), and hyperparameter bounds (e.g. `max_depth` capped).

**Q8. What is data leakage? FraudShield example?**
See `docs/data_leakage_notes.md` — fitting the `StandardScaler` on the full dataset before splitting would leak
test-set statistics into training; this project fits the scaler on train only.

**Q9. How does SHAP work at a high level?**
Attributes a prediction's probability to individual feature contributions via Shapley values (cooperative game
theory); `TreeExplainer` gives fast, exact values for tree models.

**Q10. What is a confusion matrix?**
The raw TP/FP/TN/FN counts underlying all classification metrics. Our final model: TP=13, FP=4, TN=23955,
FN=28 (on the held-out test set).

**Q11-20 rapid list:** precision, recall, F1, ROC-AUC, PR-AUC, cross-validation, why stratify a split, why fit
scaling only on train, hyperparameter tuning, `scale_pos_weight` in XGBoost — all defined and demonstrated in
`ml/src/train.py` and `docs/model_selection.md`.

## Dataset

**Q21. Which dataset and why?** See `docs/dataset_choice.md` — Kaggle-schema-compatible synthetic dataset
(ULB Credit Card Fraud structure), paired with our own synthetic live simulator.
**Q22. Class imbalance ratio?** 0.17% fraud (204 / 120,000).
**Q23. What do V1-V28 represent?** PCA-anonymized components; not individually interpretable.
**Q24. How did you validate no missing/duplicate data?** `df.isnull().sum()` and `df.duplicated().sum()` in
`ml/notebooks/02_eda_deep.ipynb` — both zero.
**Q25. Is this representative of real-world fraud today?** Honestly, no — documented as a stated limitation
(`docs/final_report.md` §31).

## Feature Engineering

**Q26-30:** See `docs/feature_plan.md` for the full synthetic feature list, why they can't be derived from the
PCA'd Kaggle columns, and the "risk-intensity" bridge used to let one trained model react to both schemas.

## Python / FastAPI / Database / React / WebSocket / Cybersecurity / API / Deployment / Testing

All covered in depth by `docs/architecture.md`, `docs/security.md`, `docs/realtime_flow.md`,
`docs/testing_strategy.md`, and the corresponding code — every viva question in the original handbook's PART 21
maps to a real, runnable piece of this repository rather than a hypothetical answer.

## Project Architecture

**Q74. Why a modular monolith instead of microservices?** A 4-month academic build doesn't need the
operational overhead of service-to-service networking, discovery, and separate deployments; NFR5 explicitly
calls for a modular monolith.
**Q75. Where does feature engineering happen?** Backend (`app/services/feature_engineering.py`), computed at
request time from the database, never client-side.
**Q76. What would break first at 10x traffic?** The single Postgres instance's connection pool and the
synchronous feature-engineering queries (multiple round-trips per prediction) — would need connection pooling
tuning and/or caching a user's rolling stats instead of recomputing them per request.
**Q78. Limitations?** See `docs/final_report.md` §31 (synthetic data, no real payment integration, ~32% recall,
manual retraining only).
**Q80. How do false positives affect real users, and how is that mitigated?** Human-in-the-loop review via the
Transaction Detail investigation page rather than fully automatic blocking — every flagged transaction requires
an admin/analyst action.
