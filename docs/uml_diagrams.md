# UML & Data Flow Diagrams (Week 17)

## Use Case Diagram (actors & use cases)
Actors: **Admin, Analyst, User (viewer), Transaction Simulator**
Use cases: Login, View Dashboard, Investigate Transaction, Resolve Alert, Manage Users, Export Report, View Audit Log.

## Sequence Diagram (Mermaid — transaction → prediction → alert → WebSocket → dashboard)

```mermaid
sequenceDiagram
    participant Sim as Simulator
    participant API as FastAPI Backend
    participant ML as ML Model
    participant DB as PostgreSQL
    participant WS as WebSocket
    participant UI as Dashboard

    Sim->>API: POST /transactions/predict
    API->>ML: predict(features)
    ML-->>API: probability, risk_score
    API->>DB: save transaction + prediction
    API->>DB: save alert (if risk >= MEDIUM)
    API->>WS: emit new_alert
    WS-->>UI: push event
    UI-->>UI: update dashboard state
```

## Class Diagram (SQLAlchemy models, mirrors PART 11 / `backend/app/models/`)

```mermaid
classDiagram
    class User {
      +int id
      +str email
      +str password_hash
      +str role
      +datetime created_at
    }
    class Transaction {
      +int id
      +int user_id
      +int merchant_id
      +int device_id
      +float amount
      +str status
      +datetime created_at
    }
    class FraudPrediction {
      +int id
      +int transaction_id
      +float probability
      +int risk_score
      +str risk_level
      +json explanation
    }
    class FraudAlert {
      +int id
      +int transaction_id
      +str severity
      +str status
      +datetime resolved_at
    }
    class AuditLog {
      +int id
      +int user_id
      +str action
      +str target_type
      +int target_id
    }
    Transaction "1" --> "1" FraudPrediction
    Transaction "1" --> "0..1" FraudAlert
    User "1" --> "many" AuditLog
```

## Activity Diagram (Decision Engine branching)

```mermaid
flowchart TD
    A[fraud_probability] --> B[risk_score = round(prob*100)]
    B --> C{risk_score range}
    C -->|0-29| D[LOW: Allow]
    C -->|30-59| E[MEDIUM: Monitor + alert]
    C -->|60-79| F[HIGH: Flag + alert]
    C -->|80-100| G[CRITICAL: Critical Alert]
```

## Component Diagram

```mermaid
flowchart LR
    subgraph Frontend
      Dash[React Dashboard]
    end
    subgraph Backend[FastAPI Backend]
      Auth[Auth]
      Txn[Transactions/Predict]
      Alerts[Alerts]
      WS[WebSocket Server]
    end
    ML[ML Model - joblib]
    DB[(PostgreSQL)]

    Dash <-->|HTTPS/WSS| Backend
    Txn --> ML
    Backend --> DB
    WS -->|events| Dash
```

## Deployment Diagram

```mermaid
flowchart LR
    U[Browser] --> V[Vercel: Frontend]
    V --> R[Render/Railway: FastAPI Backend]
    R --> P[(Managed PostgreSQL)]
```

## Data Flow Diagram — Level 1

```mermaid
flowchart LR
    TS[Transaction Source] --> TP[Transaction Processing]
    TP --> MLP[ML Prediction]
    MLP --> AL[Alerting]
    TP --> DBS[(Transactions DB)]
    AL --> ADB[(Alerts DB)]
    AL --> DR[Dashboard/Reporting]
    Admin[Administrator] --> DR
```
