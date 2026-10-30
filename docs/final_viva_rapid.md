# Final Viva Rapid Revision

1. **Problem?** Real-time detection of suspicious online transactions with explainable risk scoring.
2. **Main model?** XGBoost for supervised tabular classification.
3. **Why not accuracy?** Extreme class imbalance makes accuracy misleading.
4. **Key metrics?** Precision, recall, F1 and PR-AUC; ROC-AUC is supplementary.
5. **Anomaly model?** Isolation Forest.
6. **Why anomaly detection?** It adds a signal for unusual behavior not necessarily represented by known fraud labels.
7. **Hybrid engine?** ML + anomaly + behavioral deviation + deterministic rules.
8. **Risk score?** 0–100 decision-support score, not a raw calibrated probability.
9. **Explainability?** SHAP plus human-readable behavioral/rule reasons.
10. **Leakage prevention?** Point-in-time features and time-aware splits.
11. **Human feedback?** Analyst decisions become labeled feedback for controlled retraining.
12. **Drift?** Compare recent prediction distributions with a baseline using PSI.
13. **Graph?** Relationship analytics across users/devices/merchants; not a GNN.
14. **Security?** JWT, RBAC, bcrypt, rate limiting, input validation, parameterized queries, audit logging.
15. **Current limitation?** Synthetic/public benchmark limitations prevent production-performance claims.
16. **Most important result?** Current synthetic benchmark has XGBoost PR-AUC 0.6165 and Hybrid PR-AUC 0.6038; therefore do not claim the hybrid is the best ranking model.
