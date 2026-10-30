# Month 1 Summary (Weeks 1-4)

## Completed
- Git/GitHub repo initialized, `.gitignore` (Python + Node), README.
- Full local dev environment: Python 3.11, Node LTS, PostgreSQL 16, pgAdmin/psql tooling.
- Repo folder structure matching PART 5.
- Dataset chosen and justified (`docs/dataset_choice.md`) — synthetic, Kaggle-schema-compatible.
- EDA completed (`ml/notebooks/01_eda.ipynb`, `02_eda_deep.ipynb`; findings in `docs/eda_findings.md`).
- Preprocessing pipeline: stratified split, scaler fit on train only, leakage notes documented.
- Class imbalance strategy compared: `class_weight='balanced'` vs. SMOTE.
- Three baseline models trained: Logistic Regression, Random Forest, XGBoost.

## Baseline comparison table (class_weight='balanced', from `ml/models/model_comparison.csv`)

| Model | Precision | Recall | F1 | ROC-AUC | PR-AUC |
|---|---|---|---|---|---|
| Logistic Regression | 0.0128 | 0.9268 | 0.0253 | 0.9656 | 0.1072 |
| Random Forest | 0.6111 | 0.2683 | 0.3729 | 0.9572 | 0.3352 |
| **XGBoost** | **0.7647** | 0.3171 | **0.4483** | 0.9139 | **0.4324** |

**Observation:** Logistic Regression's `class_weight='balanced'` setting drives recall very high but precision
collapses (too many false alarms) — a textbook illustration of why precision AND recall must be reported
together (PART 10.6). XGBoost gives the best precision/PR-AUC tradeoff among the three baselines, carried
forward into Month 2's tuning (`docs/model_selection.md`).

## Synthetic feature plan
Documented in `docs/feature_plan.md`, ready for Month 3's live simulator implementation.

## Tag
`v0.1-month1` (see README's suggested Git tagging convention).
