# Model Monitoring (Week 14, Day 6)

## What is exposed

`GET /api/v1/dashboard/model-info` returns the active model's version, training date, stored offline metrics,
and the count of predictions served since the backend process started:

```json
{
  "version": "xgboost-v1",
  "trained_at": "2026-09-27T11:34:43.093289+00:00",
  "precision": 0.7647,
  "recall": 0.3171,
  "f1": 0.4483,
  "roc_auc": 0.9139,
  "pr_auc": 0.4324,
  "predictions_served": 10
}
```

Surfaced on the frontend dashboard as a small info bar above the charts (`frontend/src/pages/Dashboard.jsx`).

## Model drift & data drift (conceptual — out of scope to implement)

- **Data drift**: the statistical distribution of incoming transactions (e.g. typical amount, velocity)
  shifts away from what the model was trained on. In production, this is detected by comparing rolling
  windows of live feature distributions against the training distribution (e.g. population stability index,
  KL divergence).
- **Model drift** (a.k.a. concept drift): the *relationship* between features and the fraud label changes over
  time as fraudsters adapt — a model can look statistically fine on inputs but be systematically wrong.
  Detected in production via continuous evaluation against newly-labeled ground truth (chargebacks, confirmed
  fraud reports) and periodic retraining triggers.

**Continuous automatic retraining is explicitly out of scope for this academic prototype.** The model is
trained once (`ml/src/train.py`) and loaded at backend startup; retraining is a manual re-run of that script
followed by a backend restart.

## What a production system would add
- A scheduled batch job to re-evaluate the model weekly/monthly against freshly labeled data.
- Automated drift detection triggering an alert to the ML team (not the fraud-review dashboard).
- A model registry with staged rollout (canary → full) rather than a single `model.joblib` file.
