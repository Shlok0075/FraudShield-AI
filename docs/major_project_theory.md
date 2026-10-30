# FraudShield AI — Final-Year Project Theory

## Project title
**FraudShield AI: An Explainable Hybrid AI System for Real-Time Online Transaction Fraud Detection and Risk Monitoring**

## Core idea
FraudShield is an academic fraud-monitoring platform that combines point-in-time behavioral feature engineering, supervised machine learning, anomaly detection, deterministic rules, explainable risk scoring, investigation workflows, analyst feedback, model versioning, drift monitoring and graph-based relationship analytics.

## End-to-end flow
`Transaction -> Validation -> FeatureEngine -> XGBoost + Isolation Forest + Behavior + Rules -> Risk Aggregator -> ALLOW/REVIEW/BLOCK -> Explanation -> Alert/Case -> Analyst Decision -> Feedback -> Retraining Manifest -> Model Registry/Monitoring`

## Why point-in-time features?
A transaction must only use information available before it is scored. Future transactions or future labels create leakage and artificially improve evaluation metrics.

## Main behavioral features
- amount vs user average
- amount z-score
- transaction count over 1m/5m/1h/24h
- amount velocity
- time since previous transaction
- new device / known device count
- location change / distance / implied travel speed
- unusual hour / day / weekend
- prior user and counterparty fraud rates using matured labels

## Models
### XGBoost
Gradient-boosted decision trees used as the supervised fraud probability model. It captures nonlinear feature interactions in structured data.

### Isolation Forest
Unsupervised anomaly detector. It adds a signal for unusual behavior that may not match known fraud labels. Its score is an anomaly signal, not a calibrated fraud probability.

### Hybrid risk engine
The final risk score combines:
1. supervised ML probability,
2. anomaly score,
3. behavioral deviation score,
4. deterministic fraud-rule score.

Weights are selected using validation data. The system returns a 0–100 risk score, risk level, ALLOW/REVIEW/BLOCK decision, signal contributions, triggered rules and readable reasons.

## Explainability
SHAP-style feature attribution identifies important model contributors. The UI/API also translates technical factors into human-readable explanations such as amount deviation, new device and location change.

## Class imbalance
Fraud is usually a minority class. Accuracy can be misleading. FraudShield emphasizes precision, recall, F1 and PR-AUC, and evaluates class weighting and SMOTE where appropriate.

## Threshold and cost optimization
A default 0.5 cutoff is not assumed to be optimal. Validation data are used to select High Recall, Balanced and High Precision operating points. False positives and false negatives can be assigned different costs.

## Human-in-the-loop
Alerts become investigation cases. Analysts can add notes and label outcomes as confirmed fraud, false positive or unresolved. Feedback is stored as future training data; candidate models should be validated against the current model before deployment.

## Model registry and drift
The registry records version, dataset/feature version, metrics, threshold, artifact path and status. Prediction-distribution drift is monitored using PSI. Drift is an alerting signal, not proof that accuracy has fallen.

## Graph analytics
The graph layer models relationships such as User–Device and User–Merchant. Shared devices and concentrated relationships can reveal coordinated patterns. The current component is relational analytics, not a graph neural network.

## Simulator
The simulator generates safe, reproducible scenarios including card testing, account takeover, transaction bursts, new devices, unusual locations, transaction splitting and shared-device fraud rings. It sends transactions through the normal API.

## Security
The project uses JWT authentication, RBAC, Pydantic validation, SQLAlchemy parameterized queries, rate limiting and audit logs. Security checks are defensive tests against the local application.

## Limitations
- This is an academic prototype.
- Public/synthetic data do not establish production banking performance.
- PaySim does not contain device/location fields, so a complete live behavioral benchmark requires compatible simulated or other data.
- Current drift monitoring focuses on prediction distribution rather than full concept drift.
- Graph analytics are not a graph neural network.
- Feedback currently produces a retraining manifest; a dedicated automated retraining-and-approval job remains a future extension.
- A hybrid architecture does not automatically outperform a single model; performance claims must come from measured experiments.
