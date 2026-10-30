# Data Leakage Notes (Week 3, Day 3)

## What is data leakage?

Data leakage happens when information from outside the training data — often, information that would not be
available at real prediction time — "leaks" into the features or labels used to train a model, producing
metrics that look great offline but collapse in production.

## The classic mistake: fitting a scaler before splitting

**Wrong:**
```python
scaler = StandardScaler().fit(df[["Amount", "Time"]])       # fit on the FULL dataset
df[["Amount", "Time"]] = scaler.transform(df[["Amount", "Time"]])
X_train, X_test = train_test_split(df, ...)                 # split AFTER scaling
```
Here the scaler's mean/std were computed using statistics from rows that end up in the test set. The model's
evaluation is no longer a fair estimate of how it performs on truly unseen data — the test set's own
distribution leaked into the transformation applied to it.

**Right (what `ml/src/preprocessing.py` actually does):**
```python
train_df, test_df = stratified_split(df)      # split FIRST
scaler = fit_scaler(train_df)                 # fit ONLY on train
train_scaled = apply_scaler(train_df, scaler) # transform train
test_scaled  = apply_scaler(test_df, scaler)  # transform test with the SAME already-fitted scaler
```

## FraudShield-specific example

Imagine engineering a "user's average transaction amount" feature. If that average is computed using **all** of
a user's transactions (including ones that fall in the test set), a fraud transaction's z-score at prediction
time would implicitly "know about" future transactions that shouldn't exist yet. Our live feature engineering
(`backend/app/services/feature_engineering.py::_user_amount_stats`) avoids this by only ever considering
transactions **already persisted before** the current one — the exact same causal ordering a production system
would have to respect.

## SMOTE-specific leakage risk (Week 5)

SMOTE must only ever be applied to the **training** fold, and — when combined with cross-validation — must be
refit **inside each fold** using `imblearn.pipeline.Pipeline` (not plain `sklearn.pipeline.Pipeline`, and not
applied once before the CV loop). Applying SMOTE before splitting, or applying it to the test set, both leak
information and inflate reported recall/F1 artificially. `ml/src/train.py` calls `apply_smote()` only on
`X_train`/`y_train`, after the stratified split.
