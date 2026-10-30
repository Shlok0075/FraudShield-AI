# FraudShield AI — Final Architecture

```text
                         React / Vite Dashboard
                                  |
                         REST + WebSocket
                                  |
                         FastAPI Application
                                  |
                +-----------------+-----------------+
                |                 |                 |
           PostgreSQL        FeatureEngine       Audit Log
                |                 |
                |       +---------+---------+
                |       |         |         |
                |     XGBoost  Isolation  Rules
                |       |       Forest      |
                |       +---------+---------+
                |                 |
                |          Hybrid Risk Engine
                |                 |
                |       0–100 + decision
                |                 |
                +--------- Alert / Case --------+
                          |          |
                     Analyst      Feedback
                          |          |
                          +----+-----+
                               |
                         Candidate Training
                               |
                         Model Validation
                               |
                         Model Registry
                               |
                         Drift Monitoring
```

## Design principle
The project remains a modular monolith. The ML model is integrated into the FastAPI application rather than split into microservices. This keeps the final-year system understandable, reproducible and deployable locally.
