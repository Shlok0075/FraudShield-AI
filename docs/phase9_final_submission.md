# FraudShield AI — Phase 9 Final Submission Package

## Status
Phase 9 prepares the upgraded project for final-year report, presentation, demonstration and viva.

## Implemented architecture
- React/Vite/Tailwind frontend
- FastAPI backend
- PostgreSQL/SQLAlchemy/Alembic
- JWT authentication + RBAC
- Point-in-time behavioral feature engineering
- XGBoost supervised fraud model
- Isolation Forest anomaly signal
- Behavioral risk score
- Deterministic fraud rules
- Hybrid 0–100 risk scoring
- ALLOW/REVIEW/BLOCK decisioning
- SHAP/human-readable explanations
- Real-time WebSocket updates
- Alert and investigation cases
- Analyst feedback labels
- Model registry and activation metadata
- Prediction-distribution drift monitoring
- User profiles and merchant analytics
- Graph relationship analytics
- Fraud scenario simulator
- Security controls and audit logging

## Final ML benchmark currently available
The current synthetic behavioral benchmark produced:

| Model | PR-AUC | ROC-AUC | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| XGBoost | 0.6165 | 0.9700 | 0.5306 | 0.5532 | 0.5417 |
| FraudShield Hybrid | 0.6038 | 0.9393 | 0.5342 | 0.5532 | 0.5436 |
| Random Forest | 0.5923 | 0.9750 | 0.5630 | 0.4752 | 0.5154 |
| Logistic Regression | 0.3631 | 0.9017 | 0.1280 | 0.7305 | 0.2178 |
| Isolation Forest | 0.1267 | 0.8015 | 0.2929 | 0.2057 | 0.2417 |

These results are from a synthetic behavioral benchmark and must not be described as production banking performance.

## Academic interpretation
XGBoost has the highest PR-AUC on this benchmark. The hybrid system has a slightly higher F1 at its selected operating point, but the experiment does not establish that the hybrid ranks fraud better than XGBoost. The contribution of the hybrid system is architectural and operational: multiple complementary signals, deterministic safeguards, explanations, investigation workflows and feedback.

## Final limitations
1. Dataset representativeness is limited.
2. PaySim does not contain device/location fields required by the complete live behavioral model.
3. Synthetic scenario results are demonstrations, not real banking validation.
4. Prediction drift is monitored; full concept drift requires future labeled outcomes.
5. Graph analytics are not a graph neural network.
6. Feedback creates a controlled retraining input/manifest; automated production retraining requires a dedicated validated training pipeline.

## Recommended final claim
FraudShield AI is an academic, explainable hybrid fraud-monitoring platform demonstrating how supervised learning, anomaly detection, behavioral analytics, deterministic rules and human investigation can be integrated into a real-time transaction risk system.
