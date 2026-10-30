# FraudShield AI — Complete Project Report

### Intelligent Online Transaction Fraud Detection and Real-Time Monitoring System

**Project type:** B.Tech Final Year Academic Prototype
**Report scope:** Full system — problem, data, machine learning, backend, frontend, security, testing
**Prepared from:** the actual source code, trained model artifacts, experiment results and a live running instance

---

> ## Academic Disclaimer
>
> FraudShield AI is an **academic prototype**, not a production banking system. It operates exclusively on
> **public and synthetic data**. No real card numbers, CVVs, OTPs, merchant credentials or banking details
> appear anywhere in this project — not in the code, not in the datasets, not in the test fixtures.
>
> All transaction identifiers, users, devices, locations, amounts and timestamps are fabricated. The performance
> figures in this report are **academic results on public/synthetic datasets** and must not be read as evidence of
> real-world banking effectiveness.

---

## Table of Contents

| # | Section | Page topic |
|---|---------|-----------|
| 1 | [Introduction and Problem Statement](#1-introduction-and-problem-statement) | Why fraud detection matters |
| 2 | [Objectives](#2-objectives) | What the project set out to do |
| 3 | [Scope and Non-Goals](#3-scope-and-non-goals) | Honest boundaries |
| 4 | [Glossary of Terms](#4-glossary-of-every-term-used) | **Meaning of every technical term** |
| 5 | [System Architecture](#5-system-architecture) | How the pieces fit together |
| 6 | [Technology Stack](#6-technology-stack-and-why) | Tools and rationale |
| 7 | [Dataset](#7-the-paysim-dataset) | Data used for training |
| 8 | [Data Leakage Prevention](#8-data-leakage-prevention) | Rigour in evaluation |
| 9 | [Feature Engineering](#9-feature-engineering-the-26-live-features) | What the model sees |
| 10 | [Model Development and Evaluation](#10-model-development-and-evaluation) | 8 models compared |
| 11 | [Hybrid Risk Engine](#11-the-hybrid-risk-engine) | How the final score is made |
| 12 | [Backend API](#12-backend-api-reference) | 44 endpoints |
| 13 | [Database Design](#13-database-design) | 14 tables |
| 14 | [Frontend Dashboard](#14-frontend-dashboard) | 8 pages |
| 15 | [Real-Time Architecture](#15-real-time-architecture) | WebSocket + live feed |
| 16 | [Security](#16-security-controls) | Controls and defences |
| 17 | [Audit Trail](#17-audit-trail-and-accountability) | Who did what |
| 18 | [Testing](#18-testing-strategy-and-results) | 95 automated tests |
| 19 | [How to Run](#19-how-to-run-the-system) | Reproduction steps |
| 20 | [Results Summary](#20-results-summary) | Headline numbers |
| 21 | [Limitations](#21-limitations-and-honest-caveats) | What it cannot do |
| 22 | [Future Work](#22-future-work) | Next steps |
| 23 | [Conclusion](#23-conclusion) | Final assessment |
| A | [Appendix A — File Map](#appendix-a-complete-file-map) | Where everything lives |
| B | [Appendix B — One-Page Quick Reference](#appendix-b-one-page-quick-reference) | Revision card |

---

## 1. Introduction and Problem Statement

### 1.1 The problem

Card-not-present (CNP) fraud — fraud committed using stolen card details on online and contactless channels —
is the fastest-growing category of payment fraud worldwide. Banks and payment processors lose billions of dollars
annually to it, and the loss falls on merchants, issuers and cardholders alike.

The core difficulty is not *detecting* obviously fraudulent transactions. It is the statistical shape of the
problem:

- **Fraud is rare.** In the dataset used here, roughly **1 transaction in every 774 is fraudulent** (0.129%).
- **Fraud is not random noise.** It arrives in *patterns* — bursts of small test transactions, a sudden change of
  device and geography together, a sudden spike in amount, a transaction at an hour the account has never been
  active.
- **Missing fraud is expensive.** A real fraudulent transaction that passes through costs the institution far
  more than a false alarm that a human analyst dismisses in ten seconds.

This combination — extreme class imbalance plus subtle, multi-signal behavioural patterns — is why a naive
rule-based or threshold-based system is not sufficient, and why the problem is a genuine machine-learning problem
rather than a lookup problem.

### 1.2 Why static batch analysis is not enough

Traditional fraud systems score transactions **after the fact**, in nightly batches. This creates two failures:

1. **Detection lag.** A fraudster performing a burst of 20 transactions in 4 minutes is stopped on transaction
   number 20, not number 2. The damage is already done.
2. **No behavioural memory.** Batch scoring treats each transaction independently. It cannot know that this
   account has never transacted from this device, or that this location is 4,000 km from the previous one,
   because it has no point-in-time view of the account's own history.

FraudShield AI addresses both: every transaction is scored **synchronously as it arrives**, against features
computed from that user's history **up to that exact moment**.

### 1.3 What this project delivers

A working web platform that:

- ingests a transaction,
- computes 26 behavioural features from the account's history *as of that instant*,
- scores it using a **hybrid** of a supervised XGBoost model, an unsupervised Isolation Forest, a deterministic
  behavioural score and seven explicit fraud rules,
- produces a single **0–100 risk score**, a **risk level** and a **decision** (ALLOW / REVIEW / BLOCK),
- explains itself in plain language,
- raises an alert and opens an investigation case when warranted,
- and streams the result to an administrator's dashboard in real time.

It is backed by a genuine public-dataset benchmark: the Kaggle **PaySim** dataset, 6.36 million transactions,
evaluated with 8 model variants under a leak-free, time-aware protocol.

---

## 2. Objectives

The project was structured around the following objectives.

| # | Objective | How it was achieved | Status |
|---|-----------|---------------------|--------|
| O1 | Build a real, leak-free public-dataset benchmark | PaySim ingested, 26 point-in-time features, chronological split, 8 models compared | Achieved |
| O2 | Select a model on evidence, not preference | 8 variants × 4 operating modes compared on PR-AUC / ROC-AUC / cost | Achieved |
| O3 | Score transactions in real time, not nightly | Synchronous `POST /transactions/predict` with an in-process live feed | Achieved |
| O4 | Make the model explainable | SHAP TreeExplainer + plain-language reasons + per-signal contribution breakdown | Achieved |
| O5 | Combine statistical and deterministic detection | Hybrid engine: ML + anomaly + behavioural + 7 rules, tuned weights | Achieved |
| O6 | Provide a usable analyst workflow | Alert → Case → Note → Feedback → retraining manifest | Achieved |
| O7 | Enforce access control | JWT + bcrypt + role-based access control on every route | Achieved |
| O8 | Guarantee accountability | Audit log covering every admin action **and** failed logins | Achieved |
| O9 | Detect model degradation over time | PSI drift monitoring + model registry with activation metadata | Achieved |
| O10 | Prove the system works, not just that it starts | 95 automated tests (46 backend + 49 ML) | Achieved |

### 2.1 Non-objectives (explicitly out of scope)

- Handling real payment card data — permanently out of scope, for legal and ethical reasons.
- Building a payment gateway or transaction authoriser. This system *scores*; it does not *move money*.
- Meeting PCI-DSS, RBI or any regulatory certification.
- Production-scale throughput. The system is designed and tested for demonstration and academic evaluation.

---

## 3. Scope and Non-Goals

**In scope:** transaction scoring, feature engineering, model training and evaluation, real-time inference,
alerting, case management, feedback capture, drift monitoring, access control, audit logging, and a web dashboard.

**Deliberately not in scope, with reasons:**

| Excluded | Why |
|----------|-----|
| Real card data | Legally and ethically prohibited in an academic project; no public repository may contain PAN/CVV |
| Real-time payment authorisation | Requires banking partnerships, PCI-DSS Level 1 certification, and HSM infrastructure |
| Multi-tenant SaaS deployment | Adds billing/isolation concerns that have no bearing on the research contribution |
| Microservices | Explicitly rejected as a design decision — see §5.5 |

This section is deliberately explicit because academic reports often overstate scope. The honest claim is:
*this is a complete, working, well-tested fraud-detection prototype evaluated on a real public dataset*, not a bank.

---

## 4. Glossary of Every Term Used

This section defines every technical term appearing in this report, in plain language. It is intended to be read
standalone, so a reader unfamiliar with machine learning or web engineering can follow the rest of the document.

### 4.1 Fraud and Risk Concepts

| Term | Meaning |
|------|---------|
| **Fraud** | Deliberately deceptive activity for financial gain. In this project, a transaction is fraudulent when an authorised user did *not* make it — the card details or account were used by someone else. |
| **Fraudster** | The person committing fraud. In this project, always synthetic — there are no real attackers. |
| **Card-Not-Present (CNP) fraud** | Fraud on an online or contactless channel where the physical card is never presented, so the merchant cannot verify the signature. The dominant modern fraud type. |
| **Legitimate transaction** | A genuine transaction made by the real account holder. Also called a *negative* or *negative class* in ML. In this dataset, 99.871% of all transactions. |
| **Class imbalance** | When one class (legitimate) hugely outnumbers the other (fraud). Here 6,354,407 legitimate vs 8,213 fraudulent. Imbalance is the single biggest difficulty in fraud detection. |
| **Imbalance ratio** | The ratio of legitimate to fraudulent transactions — here about **774 : 1**. A model that simply always predicts "legitimate" would score 99.87% accuracy while detecting zero fraud. |
| **False positive (FP)** | The system flags a **legitimate** transaction as fraudulent. Costs analyst time and annoys the customer. Formally: predicted fraud, actually legitimate. |
| **False negative (FN)** | The system passes a **genuinely fraudulent** transaction. This is the dangerous error — the loss occurs. Formally: predicted legitimate, actually fraud. |
| **True positive (TP)** | Fraud correctly caught. The outcome we are trying to maximise. |
| **True negative (TN)** | A legitimate transaction correctly passed. The desired background behaviour. |
| **Precision** | Of the transactions the system flagged, what fraction were *actually* fraud? `Precision = TP / (TP + FP)`. High precision means "when I say fraud, I'm usually right." |
| **Recall** | Of all the fraud that actually happened, what fraction did the system catch? `Recall = TP / (TP + FN)`. High recall means "I don't miss fraud." |
| **Precision–Recall trade-off** | Precision and recall normally move in opposition. Lowering the decision threshold catches more fraud (recall up) but also flags more legitimate traffic (precision down). Choosing where to sit on this curve is a business decision, not a technical one. |
| **F1 score** | The harmonic mean of precision and recall: `F1 = 2 × (P × R) / (P + R)`. It is high only when *both* are high, so it punishes a model that is excellent at one and useless at the other. |
| **Threshold** | The cut-off score above which a transaction is treated as fraud. Lowering it raises recall and lowers precision. FraudShield AI uses two: a *review* threshold and a *block* threshold. |
| **Risk level** | The band a 0–100 score falls into: LOW (0–29), MEDIUM (30–59), HIGH (60–79), CRITICAL (80–100). |
| **Decision** | The action taken: **ALLOW** (let it through), **REVIEW** (hold for a human), **BLOCK** (refuse). |
| **Fraud ring** | A group of accounts colluding to launder stolen funds, often by passing small amounts between themselves to appear normal. |
| **Card testing** | An attacker making several tiny transactions to confirm a stolen card number is live before using it for a real purchase. |
| **Transaction velocity** | How *fast* transactions are occurring — the rate of change, not just the count. Six transactions in 5 minutes is a different signal from six in 6 months. |
| **Impossible travel** | A user appearing in two locations too far apart for the time elapsed between the two transactions — implying the account is being used from two places at once. |
| **First-party fraud** | Fraud committed by the account holder themselves. **Out of scope here** — this system targets *third-party* (account takeover) fraud. |
| **Chargeback** | A cardholder reversing a transaction through their bank. The mechanism by which fraud costs merchants money. |
| **CNA / CNP** | *Card-Not-Authenticated* / *Card-Not-Present*. The electronic equivalent of a CNP transaction. |

### 4.2 Data Science and Machine Learning

| Term | Meaning |
|------|---------|
| **Machine Learning (ML)** | Software that learns patterns from data instead of being given explicit rules. Here, it learns what a fraudulent transaction looks like from labelled examples. |
| **Supervised learning** | Learning from data where the answer is already known ("this one *is* fraud"). The model learns input → correct output. |
| **Unsupervised learning** | Learning structure in data *without* answers. Useful for finding "odd" transactions nobody has yet labelled as fraud. |
| **Model** | The learned function that maps inputs to a fraud probability. Once trained, it is a fixed set of parameters. |
| **Training** | The process of fitting model parameters to data. The model "studies" the training set. |
| **Feature** | An individual input column the model uses — e.g. `amount`, `txn_count_5m`, `new_device`. Also called an *attribute* or *predictor*. |
| **Feature engineering** | The craft of choosing and constructing the most informative features. Usually where most of a real project's predictive power comes from. |
| **Label / Target** | The correct answer for a training example (`1` = fraud, `0` = legitimate). |
| **Ground truth** | The verified real answer, independent of what a model predicts. Used to measure the model. |
| **Inference / Prediction** | Applying a trained model to new data to produce a prediction. |
| **XGBoost** | *Extreme Gradient Boosting.* A gradient-boosted decision-tree method — the model used for the primary fraud classifier here. Fast, accurate, handles imbalanced tabular data well. |
| **Gradient boosting** | Builds an ensemble of decision trees one at a time, each new tree correcting the errors of the previous ones. |
| **Decision tree** | A model that predicts by asking a chain of yes/no questions (`amount > 50000? → is device new? → …`). |
| **Ensemble** | A combination of several models whose combined prediction is better than any single one. |
| **Isolation Forest** | An **unsupervised** anomaly detector. It randomly partitions the feature space; points that end up isolated in few splits are treated as unusual. Needs no fraud labels. |
| **Anomaly** | A transaction unlike the norm. Not necessarily fraud — it is a *candidate* signal, not a verdict. |
| **Supervised vs unsupervised in this system** | XGBoost is supervised (needs fraud labels). Isolation Forest is unsupervised (finds oddity without labels). Both contribute to the final score. |
| **Logistic regression** | A simple linear model that outputs a probability. Interpretable but limited — it learns a straight-line boundary. |
| **Random Forest** | An ensemble of many decision trees, each voting. Robust, but slow at inference and large on disk. |
| **SMOTE** | *Synthetic Minority Over-sampling Technique.* Creates synthetic minority examples to balance the training set. Used here as one experimental strategy. |
| **Class weight** | The alternative to SMOTE for imbalance: instead of adding data, tell the model "mistakes on fraud cost 100× more than mistakes on legitimate." |
| **Imbalance strategy** | The specific method used to handle class imbalance. This project compared: none, class weighting, and SMOTE. |
| **Feature importance** | How much each feature influenced the model's predictions. Interpretable, but coarser than SHAP. |
| **SHAP** | *SHapley Additive exPlanations.* A method from game theory that attributes a prediction to individual features — "this score is 0.82, of which 0.31 came from the new device." |
| **Explainability / Interpretability** | The ability to justify a specific prediction in human terms. Essential in fraud: an analyst must be able to say *why*. |
| **Probability** | The model's confidence, 0 to 1, that a transaction is fraudulent. *Not* the same as the final risk score. |
| **Cold start** | When a new user or account has no history, so behavioural features have nothing to compare against. Handled here with documented safe defaults rather than crashes or `NaN`. |
| **Baseline** | A user's normal behaviour, established from their own history. Every behavioural feature is a *deviation from this baseline*. |
| **Point-in-time correctness** | Computing features using only data that existed **before** the transaction being scored. Violating this is data leakage (see §8). |
| **Hyperparameter** | A setting chosen *before* training (e.g. tree depth, learning rate, number of trees), as distinct from a learned parameter. |
| **Model artefact** | The saved file containing a trained model, e.g. `supervised.joblib`. Loading it is how the model is used in production. |
| **Feature schema** | The ordered, frozen list of feature names the model was trained on. The live path must produce features in exactly this order. |
| **Median imputation** | Replacing a missing feature value with the training-set median rather than a zero, so a missing value is not silently treated as "nothing unusual." |

### 4.3 Model Evaluation Metrics

| Term | Meaning |
|------|---------|
| **ROC curve** | A graph of true-positive rate against false-positive rate across all possible thresholds. |
| **ROC-AUC** | *Area Under the ROC Curve.* **1.0 = perfect, 0.5 = random guessing.** Measures ranking quality across all thresholds. Less informative than PR-AUC for heavily imbalanced data. |
| **Precision-Recall curve (PR curve)** | Precision against recall across thresholds. |
| **PR-AUC** | Area under the PR curve. **The primary metric for this project**, because it stays honest under extreme imbalance where ROC-AUC flatters a model. Best here: 0.5203. |
| **Base rate** | The natural fraction of positives in the data (0.329% in the test split). A PR-AUC must be compared against this — 0.0033 would be worthless. |
| **Brier score** | Mean squared error between predicted probability and actual outcome. Lower is better; measures whether probabilities are *calibrated*, not just correctly ordered. |
| **Confusion matrix** | A 2×2 table of TP / FP / FN / TN summarising all predictions at one threshold. |
| **FPR / FNR** | *False Positive Rate* and *False Negative Rate* — the proportion of legitimate or fraudulent transactions respectively that were misclassified. |
| **Cost matrix** | Assigning money to each error type. This project used **₹-equivalent cost 5 per false positive, 500 per false negative** — a 100:1 ratio reflecting that missing real fraud is far more damaging. |
| **Minimum-cost operating point** | The threshold that minimises total expected cost under the cost matrix — the economically correct operating point, even if it has a lower F1. |
| **Operating mode** | A named (threshold, objective) pair. This project defines four: `high_recall`, `high_precision`, `balanced`, `min_cost`. |
| **Overfitting** | A model that memorised the training data, so it performs well in training and poorly on new data. Detected by comparing train and test metrics. |
| **Underfitting** | A model too simple to capture the pattern, performing poorly everywhere. |
| **Data leakage** | Information that should not be available at prediction time leaking into training, producing misleadingly perfect scores. See §8. |
| **Validation set** | Data held out from training, used to *choose* hyperparameters and thresholds. |
| **Test set** | Data touched exactly once, at the very end, to report final numbers. Choosing anything using it invalidates it. |
| **Cross-validation** | Rotating train/validation splits to reduce dependence on one particular split. This project instead used a time-aware split, which is more appropriate. |
| **Chronological split** | Splitting by *time* (earlier rows train, later rows test) rather than randomly. Essential for time-series data: a random split lets a model "see the future" while predicting the past. |
| **Baseline model** | A deliberately simple reference model a better model must beat. Here, logistic regression. |

### 4.4 Software Engineering and Web Technology

| Term | Meaning |
|------|---------|
| **Front end / Back end** | **Front end** = what the user sees and clicks (the dashboard). **Back end** = the server logic and database behind it. |
| **REST API** | A set of rules for a server to expose functionality over HTTP using standard verbs (`GET` read, `POST` create, `PATCH` update, `DELETE` remove). |
| **Endpoint** | One specific URL + method combination that performs one function, e.g. `POST /api/v1/auth/login`. |
| **HTTP status code** | A 3-digit result code. `200` OK, `201` Created, `401` not authenticated, `403` authenticated but not allowed, `404` not found, `422` validation failed, `429` rate limited. |
| **JSON** | A lightweight text format for structured data exchange. The format of every API response here. |
| **Request / Response** | A client asking for something; the server's answer. |
| **Payload** | The data carried inside a request or response. |
| **Serialisation** | Converting an object into bytes (to save or send) and back. |
| **ORM** | *Object-Relational Mapping.* Lets code use Python classes instead of hand-writing SQL. SQLAlchemy is the ORM used here. |
| **SQL** | *Structured Query Language* — the language databases are queried in. |
| **SQL injection** | An attack where user input is pasted into a SQL query to hijack the database. Prevented here by parameterised queries via the ORM. |
| **Table / Row / Column** | A table is a data grid; a row is one record; a column is one attribute. |
| **Primary key / Foreign key** | A **primary key** uniquely identifies a row. A **foreign key** links one table's row to another table's row. |
| **Index** | A data structure that makes lookups fast at the cost of slower writes. |
| **Migration** | A versioned, scripted change to the database *schema* (structure), recorded in order so the database can be rebuilt to any point. Alembic manages these here. |
| **Schema** | The structure of the database — which tables and columns exist. Distinct from a Pydantic "schema" (a data-shape definition), which is a different meaning of the same word. |
| **Dependency injection / override** | Supplying a test double in place of the real database, so tests are isolated and fast. |
| **FastAPI** | A modern Python web framework that builds an API and auto-generates interactive documentation from type hints. |
| **Uvicorn** | The ASGI server that actually runs a FastAPI application. |
| **ASGI** | *Asynchronous Server Gateway Interface* — the standard Python web servers use to run async applications. |
| **React** | A JavaScript library for building user interfaces from reusable components. |
| **Vite** | The modern build tool and dev server for the frontend. Compiles JSX into browser-ready JavaScript. |
| **JSX** | JavaScript extended with HTML-like tags, so UI structure can be written inline with component logic. |
| **Component** | A reusable, self-contained piece of a user interface. |
| **Hooks** | React functions that let a component use state and lifecycle, e.g. `useState`, `useEffect`. |
| **SPA** | *Single-Page Application* — a web app that updates one page without reloading the browser. |
| **Axios** | An HTTP client for JavaScript — the frontend's way of calling the API. |
| **Tailwind CSS** | A utility-first styling framework: styling is applied with small predefined classes rather than a separate stylesheet. |
| **Recharts** | A charting library for React, used for the dashboard graphs. |
| **Responsive container** | A chart that resizes itself to fit its parent element. |
| **WebSocket** | A persistent two-way connection that stays open, so the server can push updates instantly without the browser polling. |
| **Socket.IO** | A library that manages WebSocket connections with automatic reconnection. |
| **ASGI mount** | Attaching a real-time server to the same HTTP server and port as the API, so one process serves both. |
| **Event / broadcast** | A message pushed to connected clients, e.g. "transaction 501 scored CRITICAL". |
| **Vite dev server / build** | `npm run dev` serves the app live with hot reload; `npm run build` compiles it for deployment. |
| **npm** | The package manager for JavaScript libraries. |
| **Environment variable** | A setting read from outside the code (e.g. `DATABASE_URL`), so secrets never sit in source. |
| **`.env` file** | A local file holding environment variables, kept out of version control. |

### 4.5 Security and Access Control

| Term | Meaning |
|------|---------|
| **Authentication** | Proving *who you are* — the login step. |
| **Authorisation** | Deciding *what you may do* once identity is known. Authentication without authorisation is an open door. |
| **RBAC** | *Role-Based Access Control.* Permissions attach to roles (`admin`, `analyst`, `user`), not to individual people. |
| **Role** | A named permission bundle: `admin` (full access), `analyst` (read data, work cases), `user` (minimal). |
| **Privilege escalation** | Gaining permissions you were not granted. A classic vulnerability, tested against in this project. |
| **JWT** | *JSON Web Token.* A signed, self-contained token that carries identity and role, so the server need not store sessions. |
| **Token expiry** | A JWT has a limited validity (60 minutes here). After that it must be re-issued. Limits the damage if a token is stolen. |
| **HS256** | The signing algorithm used for these JWTs. "Signed" means the server can detect tampering. |
| **bcrypt** | A deliberately slow, salted password-hashing function. Slow on purpose, so brute-forcing a stolen hash is expensive. |
| **Hashing** | One-way conversion of a password to a fixed-length fingerprint. Cannot be reversed. |
| **Salt** | A unique random value mixed into each password before hashing, so identical passwords produce different hashes and precomputed "rainbow tables" are useless. |
| **Plaintext** | Text stored without protection. This project never stores a password in plaintext, anywhere. |
| **Brute force** | Trying every possible password until one works. Defended here by rate limiting. |
| **Rate limiting** | Capping how many requests one client may make per minute. Login: 10/min. Prediction: 60/min. |
| **CORS** | *Cross-Origin Resource Sharing.* The browser rule that decides which other domains may call this API. A wildcard `*` is unsafe; this project uses an explicit allow-list. |
| **HTTPS / TLS** | Encrypted transport. Required in any real deployment so tokens cannot be intercepted. |
| **Audit log** | An append-only record of who did what, when, from where. Evidence after the fact. |
| **Audit trail integrity** | Audit entries are never edited or deleted, so they remain trustworthy. |
| **PII** | *Personally Identifiable Information* — data that identifies a person. Minimising it is a legal and ethical duty. |
| **Least privilege** | Giving each account only the permissions it needs, no more. |
| **Injection attack** | Malicious input that changes a command's meaning. Includes SQL injection and XSS. |
| **XSS** | *Cross-Site Scripting* — injecting malicious JavaScript into a page. |
| **Threat model** | A structured statement of what could go wrong, who the attacker is, and which controls address each risk. |
| **Security event** | A recorded observation from a security check, e.g. "SQL-injection payload correctly rejected with 422". |

### 4.6 Database and Operations

| Term | Meaning |
|------|---------|
| **PostgreSQL** | A production-grade open-source relational database. |
| **SQLite** | A single-file relational database. No server needed — used for local runs and automated tests. |
| **ACID** | The four guarantees a relational database provides: **A**tomicity, **C**onsistency, **I**solation, **D**urability. |
| **Transaction (DB sense)** | A unit of work that either fully succeeds or fully fails. Distinct from a *payment* transaction, which is what this project mainly stores. |
| **Commit** | Making a change permanent. |
| **Session** | A temporary connection context holding state for a block of work. |
| **Pool** | A cache of reusable database connections, so connecting is not repeated per request. |
| **Rollup** | A pre-aggregated summary table, so a 6.36-million-row question is answered from a few hundred rows. A standard performance technique. |
| **Ingestion** | Loading raw data into the system. |
| **ETL** | *Extract, Transform, Load* — the general shape of every data pipeline. |
| **Counting rows** | A full scan, slow on millions of rows. Typically avoided by filtering on an indexed, narrow range. |
| **Index range** | Restricting a query to a slice of ids, e.g. `id >= 0`, so it touches far fewer rows. |
| **Process-wide singleton** | One shared instance for the whole application, so there is only ever one live feed. |
| **Background task** | Work that runs concurrently without blocking the response to a request. |
| **Lifespan** | The application's start-up and shutdown sequence, where long-running background work is started and stopped. |
| **UUID / Primary key sequence** | How unique identifiers are generated. This project uses an explicit allocator so live ids start at 0. |
| **Negative identifier space** | Reserving negative ids so training-corpus rows and live rows can live in one table without ever colliding. |
| **Health endpoint** | A trivial endpoint answering "is this process alive?" — used for monitoring. |
| **OpenAPI / Swagger** | A machine-readable description of an API, rendered as interactive documentation. |

### 4.7 MLOps and Monitoring

| Term | Meaning |
|------|---------|
| **MLOps** | The practice of operating ML systems in production — deployment, monitoring, retraining. |
| **Model registry** | A catalogue of trained model versions with their metrics, so a model can be traced, compared and rolled back. |
| **Model versioning** | Keeping every trained model with an identifier, so results are reproducible. |
| **Activation** | Choosing which registered model version is currently serving traffic. |
| **Drift** | When live data stops resembling the training data, so the model's predictions degrade. |
| **Concept drift** | The relationship between inputs and the true outcome changes over time (fraud tactics evolve). |
| **Data drift** | The distribution of input features changes over time. |
| **PSI** | *Population Stability Index.* Measures how far a distribution has shifted from a baseline. Conventionally: < 0.10 stable, 0.10–0.25 moderate shift, > 0.25 significant. |
| **Monitoring** | Continuously checking the live system for degradation, as opposed to testing it once. |
| **Retraining manifest** | A record describing what to retrain on, from analyst feedback, without retraining automatically. |
| **Feedback loop** | Analyst judgement → feedback record → retraining candidate → new model version. Closes the loop between human expertise and model. |
| **Ground-truth lag** | Real fraud labels arrive long after the transaction (here, 24 hours). A model must be trained without labels that do not exist yet. |
| **Champion/challenger** | Comparing a candidate model against the incumbent before promoting it. |

---

## 5. System Architecture

### 5.1 Overview diagram

```text
                          ┌──────────────────────────┐
                          │   React / Vite Dashboard │
                          │  Dashboard · Alerts ·    │
                          │  Cases · Audit · Users   │
                          └────────────┬─────────────┘
                                       │  REST (HTTP) + WebSocket
                          ┌────────────┴─────────────┐
                          │      FastAPI Backend     │
                          │  routes · schemas · auth │
                          └────┬──────────┬──────┬───┘
                               │          │      │
              ┌────────────────┘          │      └───────────────┐
              ▼                           ▼                      ▼
   ┌────────────────────┐   ┌──────────────────────┐   ┌──────────────────┐
   │  FeatureEngine     │   │  Hybrid Risk Engine  │   │  Audit Service   │
   │  26 point-in-time  │   │  ML + anomaly +       │   │  every admin     │
   │  behavioural feats  │   │  behaviour + rules   │   │  action logged   │
   └─────────┬──────────┘   └──────────┬───────────┘   └──────────────────┘
             │                         │
             │            ┌────────────┼────────────┐
             │            ▼            ▼            ▼
             │      ┌──────────┐ ┌────────────┐ ┌──────────┐
             │      │ XGBoost  │ │Isolation   │ │ 7 fraud  │
             │      │(supervised)│ │  Forest    │ │  rules   │
             │      └──────────┘ │(unsupervised)│ └──────────┘
             │                  └────────────┘
             │                         │
             │                    0–100 score
             │                         ▼
             │                   ALLOW / REVIEW / BLOCK
             │                         │
   ┌─────────┴─────────────────────────┴──────┐
   ▼                   Database                 │
┌─────────────────┐  ┌──────────┐  ┌────────────┴────┐
│  Transaction    │  │ Fraud    │  │  Alert → Case   │
│  + Prediction   │  │ Alert    │──▶  → Note →       │
└─────────────────┘  └──────────┘   │  Feedback       │
                                     └─────────────────┘
```

### 5.2 The single-transaction path

Every transaction — whether it arrives from an HTTP client or from the built-in live feed — takes **exactly one
path**. This is enforced in code: both callers invoke the same function,
`services/prediction_pipeline.ingest_transaction()`.

The order of operations matters, and the order is deliberate:

1. **Build features *before* persisting anything.** If the transaction were stored first, "is this a new
   device?" would compare the device against itself and always answer *no*. Computing features first is what
   makes the new-device signal correct, and it is the single most important ordering constraint in the pipeline.
2. **Score** — XGBoost probability, Isolation Forest anomaly, behavioural score, and deterministic rules
   combined into one 0–100 score.
3. **Register the device**, only now, so a genuinely new device is detectable next time.
4. **Persist the transaction**, then the prediction with its full explanation.
5. **Create an alert and a case** if the decision is REVIEW or BLOCK.
6. **Emit WebSocket events** so every connected dashboard updates instantly.

### 5.3 Live data vs training corpus

The system holds two logically distinct populations in one database:

| Population | Identifier range | Purpose | Counted in dashboard KPIs? |
|-----------|------------------|---------|---------------------------|
| **PaySim training corpus** | Negative ids, `-10,000,000 … -3,637,381` | Offline training and benchmark reporting | **No** |
| **Live traffic** | Non-negative ids, starting at `0` | Real-time scoring and operations | **Yes** |

This separation exists because mixing them produces a dishonest dashboard. If the 6.36-million-row corpus were
counted as "transactions processed today", the headline number would be meaningless — it would describe training
data, not activity. Corpus figures are reported separately and explicitly labelled as training data.

The allocator is explicit rather than relying on a database auto-increment sequence, precisely so that
continuing the live counter can never collide with the corpus range.

### 5.4 Real-time flow

```text
  Browser                    Backend                      Model
    │                            │                           │
    │  WS connect                │                           │
    │───────────────────────────▶│                           │
    │                            │                           │
    │                            │  transaction arrives     │
    │                            │──────────────────────────▶│
    │                            │      score 0–100          │
    │                            │◀──────────────────────────│
    │  ◀── "txn 501 CRITICAL" ───│  (pushed, not polled)    │
    │                            │                           │
```

The dashboard never polls. When a transaction is scored, the backend pushes an event to every connected client.

### 5.5 Architectural decision: modular monolith

The ML model is integrated **into** the FastAPI application rather than split into microservices.

*Why:* a microservices split would add service discovery, network failure modes, distributed tracing and
container orchestration — substantial machinery that adds risk without adding research value. For a final-year
project that must be understandable, reproducible and locally deployable, a **modular monolith** is the correct
choice: clear internal module boundaries, one deployable unit, one database transaction spanning the whole
scoring flow.

This is a deliberate, defensible engineering decision rather than an omission.

---

## 6. Technology Stack and Why

### 6.1 Frontend

| Technology | Version | Why it was chosen |
|-----------|---------|-------------------|
| React | 19.x | Component model maps cleanly onto dashboard widgets; largest ecosystem |
| Vite | 8.x | Fast dev server with hot reload; modern build tooling |
| Tailwind CSS | 4.x | Utility classes keep styling consistent without a large stylesheet |
| Recharts | 3.x | Composable React charts for trends and distributions |
| Axios | 1.x | Promise-based HTTP client with interceptors |
| socket.io-client | 4.x | WebSocket with automatic reconnection — a dropped connection heals itself |
| oxlint | 1.x | Fast JavaScript linting |

### 6.2 Backend

| Technology | Version | Why it was chosen |
|-----------|---------|-------------------|
| FastAPI | 0.141 | Async Python, automatic OpenAPI docs, Pydantic validation built in |
| Uvicorn | 0.54 | ASGI server for FastAPI |
| SQLAlchemy | 2.1 | ORM — parameterised queries, so SQL injection is structurally prevented |
| Alembic | 1.20 | Versioned schema migrations |
| Pydantic | 2.13 | Request/response validation; invalid input is rejected before reaching the database |
| python-jose | 3.5 | JWT creation and verification |
| passlib + bcrypt | 1.7 / 4.0 | Password hashing |
| slowapi | 0.1 | Rate limiting for login and prediction endpoints |
| python-socketio | 5.17 | Real-time events, mounted on the same server |
| psycopg2-binary | 2.9 | PostgreSQL driver |
| pytest | 9.1 | Automated testing |

### 6.3 Machine learning

| Technology | Why it was chosen |
|-----------|-------------------|
| pandas / NumPy | Data manipulation and vectorised numerics |
| scikit-learn | Preprocessing, metrics, model baselines |
| XGBoost | Primary classifier — best PR-AUC on the benchmark and fast enough for real time |
| imbalanced-learn | SMOTE oversampling, as one experimental imbalance strategy |
| SHAP | Per-prediction feature attribution for explainability |
| joblib | Model serialisation |

### 6.4 Database

PostgreSQL 16 for deployment; SQLite for local demonstration and automated tests. SQLAlchemy abstracts the
difference, and the test suite deliberately uses in-memory SQLite so CI needs no external database service.

---

## 7. The PaySim Dataset

### 7.1 Provenance

| Property | Value |
|----------|-------|
| **Name** | PaySim — *Synthetic financial transaction dataset for fraud detection* |
| **Publishers** | Lopez-Rojas et al. |
| **Availability** | Public, via Kaggle (`ealaxi/paysim1`) |
| **File** | `PS_20174392719_1491204439457_log.csv` |
| **SHA-256** | `16910f90577b0d981bf8ff289714510bb89bc71bff7d3f220f024e287e4eea6b` |
| **Nature** | **Synthetic** — generated for research, containing no real financial data |
| **Time span** | 742 hours (~31 days) |
| **Fraud rate** | 0.1291% — about 1 in 774 transactions |

The SHA-256 checksum is recorded in `dataset_meta.json` so anyone can verify they are using the identical file
the results were produced from. This is basic research hygiene.

### 7.2 Raw columns

| Original column | Kept? | Reason |
|-----------------|-------|--------|
| `step` (days since start) | ✅ | Time source for velocity and hour-of-day features |
| `type` (transaction type) | ✅ | Payment-type signal |
| `amount` | ✅ | Primary monetary feature |
| `nameOrig` / `nameDest` | ✅ (hashed) | Counterparty identity |
| `oldbalanceOrig`, `newbalanceOrig`, `oldbalanceDest`, `newbalanceDest` | ❌ **Dropped** | **Leakage risk** — see §8.1 |
| `isFlaggedFraud` | ❌ **Dropped** | **Leakage** — it is the source label, and PaySim's flag is itself a known-biased heuristic |
| `isFraud` | ✅ as the label | The target variable |

PaySim's own `isFlaggedFraud` is a *simulator artefact* derived from the generative process, not an independent
verdict. Keeping it as a feature would let the model read the answer. It is dropped and the more reliable
`isFraud` ground truth is used instead.

### 7.3 Processed dataset profile

| Property | Value |
|----------|-------|
| Total rows | **6,362,620** |
| Fraud rows | **8,213** |
| Fraud rate | 0.1291% |
| Missing values | **0** in every column |
| Duplicate rows | **0** |
| Unique users | 6,353,307 |
| Unique counterparties | 2,722,362 |
| Users with >1 transaction | 0.146% |
| Maximum transactions per user | **3** |

### 7.4 Fraud distribution by transaction type

| Type | Rows | Fraud | Fraud rate within type |
|------|------|-------|-----------------------|
| CASH_OUT | 2,237,500 | 4,116 | 0.184% |
| TRANSFER | 532,909 | 4,097 | 0.769% |
| CASH_IN | 1,399,284 | 0 | 0% |
| PAYMENT | 2,151,495 | 0 | 0% |
| DEBIT | 41,432 | 0 | 0% |

**Interpretation.** All fraud in PaySim sits in CASH_OUT and TRANSFER — the two types that move money *out* of an
account. This is a property of the synthetic generative process, not a finding about real banking. A real-world
model must not assume fraud is impossible in other transaction types; this concentration is an **artefact** and
is reported as a limitation in §21.

### 7.5 Split

A **chronological** split is used, not a random one, because randomly splitting time-series data lets a model
train on data that is *later* than the data it is asked to predict.

| Split | Fraction | Rows | Fraud | Fraud rate |
|-------|----------|------|-------|-----------|
| Train | 60% | 3,792,821 | 3,175 | 0.0837% |
| Validation | 20% | 1,276,276 | 780 | 0.0611% |
| Test | 20% | 1,293,523 | 4,258 | **0.3292%** |

The test fraud rate (0.329%) is substantially higher than training (0.084%). This is **temporal variation
inherent to the data**, not a bug — and it is a useful stress test, because a model tuned on the quiet training
period must still work in the busy test period. It is also a genuine difficulty: the model is selected in a calm
regime and must perform in a turbulent one.

### 7.6 Label availability delay

Fraud ground truth arrives **24 hours (86,400 s) after** the transaction. This `label_delay_s` is respected
throughout feature construction: a feature computed at time *t* may only use transactions from before *t*,
because a label from the future does not exist at decision time.

---

## 8. Data Leakage Prevention

Data leakage — letting information that would not exist at prediction time influence training — is the most
common way fraud models appear to work brilliantly and then fail in production. Three specific leaks were
identified and closed.

### 8.1 Post-balance columns (`oldbalance*`, `newbalance*`)

PaySim provides the account balance before and after each transaction. These are computed *from the outcome*:
a balance is only "new" after the money has moved. A fraudulent transaction typically empties an account, so
post-transaction balances leak the answer almost directly.

**Action:** all four balance columns dropped at ingestion.

### 8.2 The simulator's own fraud flag (`isFlaggedFraud`)

This flag is generated by the same process that generated the transactions, encoding the generative rule rather
than an independent judgement. It correlates with the label by construction.

**Action:** dropped. `isFraud` used as the label instead.

### 8.3 Future information in behavioural features

A velocity feature ("transactions in the last 5 minutes") is legitimate — but only if "last 5 minutes" means
*before* the current transaction. Computing it over the whole window including the current row would let a
single burst transaction raise its own velocity score.

**Action:** every behavioural feature is computed **point-in-time**, using only strictly earlier transactions.
This is enforced structurally: in the live pipeline, `build_features()` runs *before* the current transaction
is persisted, so the current row cannot appear in its own history.

**Verification:** `docs/data_leakage_notes.md` records the analysis. The test suite asserts that corpus rows
(negative ids) never influence live scoring — a corpus row is not a real transaction and must not be counted.

### 8.4 Why the test set is touched once

Thresholds are selected on the **validation** set. The test set is evaluated exactly once, at the end, at those
frozen thresholds. Choosing a threshold by looking at test performance would silently convert the test set into
a second validation set and inflate every reported number.

---

## 9. Feature Engineering — the 26 Live Features

Every feature is a **deviation from a baseline built from that account's own history**, computed strictly
point-in-time. The live model uses 26 features, grouped below by the signal they capture.

### 9.1 Amount features

| Feature | Definition | Fraud signal it captures |
|---------|-----------|-------------------------|
| `amount` | Raw transaction amount | Baseline magnitude |
| `log_amount` | `log1p(amount)` | Compresses extreme values so one huge transaction cannot dominate the tree splits |
| `amount_vs_user_avg` | `amount / mean(prior amounts)` | An amount 20× the account's norm is suspicious |
| `amount_zscore` | `(amount − μ) / σ` over the user's own history | How many standard deviations from normal |

### 9.2 Velocity features — *how fast*, not just *how many*

| Feature | Definition | Fraud signal it captures |
|---------|-----------|-------------------------|
| `txn_count_1m` | Transactions in the last 1 minute | Card testing, bursts |
| `txn_count_5m` | Transactions in the last 5 minutes | Card testing, rapid repetition |
| `txn_count_1h` | Transactions in the last hour | Sustained anomalous activity |
| `txn_count_24h` | Transactions in the last 24 hours | Daily volume deviation |
| `amount_sum_1h` | Total amount in the last hour | Sudden drain attempt |
| `amount_sum_24h` | Total amount in the last 24 hours | Large outflow |
| `time_since_last_txn_s` | Seconds since this user's previous transaction | Machine-like regularity indicates automation |

### 9.3 Account lifecycle features

| Feature | Definition | Fraud signal it captures |
|---------|-----------|-------------------------|
| `user_txn_count_prior` | Number of prior transactions | How much history exists |
| `is_first_txn` | 1 if this is the account's first transaction | Brand-new accounts are high-risk |
| `account_age_s` | Seconds since the account was first seen | Very new accounts |

### 9.4 Time-of-day features

| Feature | Definition | Fraud signal it captures |
|---------|-----------|-------------------------|
| `hour_of_day` | Hour (UTC) of the transaction | Context |
| `day_of_week` | Day of week | Context — weekends differ |
| `is_weekend` | 1 if Saturday or Sunday | Context |
| `unusual_hour` | 1 if the hour is rare for this user | Activity at 03:00 for a 09:00–18:00 account |

### 9.5 Counterparty features

| Feature | Definition | Fraud signal it captures |
|---------|-----------|-------------------------|
| `counterparty_txn_count_prior` | Prior transactions with this counterparty | New payee |
| `user_fraud_rate_prior` | User's historical share of HIGH/CRITICAL predictions | Account already implicated |
| `counterparty_fraud_rate_prior` | Counterparty's confirmed-fraud rate | Destination already implicated |

### 9.6 Device and geography features

| Feature | Definition | Fraud signal it captures |
|---------|-----------|-------------------------|
| `new_device` | 1 if this device has never been seen for this user | Stolen card on unknown hardware |
| `known_device_count` | How many devices this user is associated with | New device on a multi-device account is more suspicious |
| `location_change` | 1 if the location differs from the previous transaction | Travel |
| `distance_from_prev_km` | Great-circle distance from the previous location | Geographic impossibility |
| `implied_speed_kmh` | `distance / elapsed time` | **Impossible travel** — above 900 km/h is physically impossible |

### 9.7 The "impossible travel" derivation

This is the most interpretable feature in the system, and it is pure geometry:

```text
implied_speed_kmh = distance_from_prev_km
                   ─────────────────────────────
                   (time_now − time_of_previous_txn) in hours
```

If a user's previous transaction was in Mumbai and the current one is in Chennai 1.2 hours later, the implied
speed is roughly 1,000 km/h — faster than a commercial aircraft. No human made both transactions. This single
feature catches account takeover without needing any fraud label, which is why it also operates as a standalone
deterministic rule.

### 9.8 Cold-start handling

A user with no history would make `amount_vs_user_avg` a division by zero and `amount_zscore` undefined. Rather
than crash or produce `NaN`:

- `mean_amount = 0`, `std_amount = 1` for a brand-new account, so the z-score degenerates gracefully to the raw
  amount.
- The **behavioural score** is scaled by a *history confidence* factor, `min(1, prior_txns / 5)`. An account with
  no history is simply not judged against a meaningless baseline — it accumulates weight as real history arrives.
- A first transaction is still scored, but its `is_first_txn` flag contributes its own honest risk signal.

---

## 10. Model Development and Evaluation

### 10.1 Protocol

A strict, leak-free protocol was followed:

1. **Fit** on the training split only.
2. **Select** every threshold on the **validation** split, never on test.
3. **Evaluate** the test split exactly once, at those frozen thresholds.

This discipline is what makes the numbers in §10.3 trustworthy.

### 10.2 The eight model variants

Three algorithm families × three imbalance strategies, plus one unsupervised model:

| ID | Model | Imbalance strategy | Kind |
|----|-------|-------------------|------|
| A | Logistic Regression | none | supervised |
| A2 | Logistic Regression | `class_weight='balanced'` | supervised |
| B | Random Forest | none | supervised |
| B2 | Random Forest | `class_weight='balanced'` | supervised |
| C | XGBoost | none | supervised |
| D | XGBoost | `class_weight='balanced'` | supervised |
| E | XGBoost | SMOTE | supervised |
| F | Isolation Forest | n/a | **unsupervised** |

### 10.3 Test-set results

All figures are on the **test split** (1,293,523 rows, 4,258 fraud) at each model's best-validation operating
point. Base rate = 0.329%.

| Model | PR-AUC | ROC-AUC | Brier | Median latency | Fit time |
|-------|--------|---------|-------|----------------|----------|
| A — LogReg | 0.2320 | 0.9024 | 0.0029 | 2.4 ms | 18 s |
| A2 — LogReg (balanced) | 0.1292 | 0.9381 | 0.1146 | 1.2 ms | 37 s |
| B — Random Forest | 0.4375 | 0.9609 | 0.0034 | 110 ms | 134 s |
| B2 — Random Forest (balanced) | 0.4583 | 0.9696 | 0.0064 | 76 ms | 136 s |
| C — XGBoost | 0.3056 | 0.9706 | 0.0034 | 7.3 ms | 315 s |
| **D — XGBoost (balanced)** | **0.5203** | 0.9665 | 0.0358 | **7.2 ms** | 226 s |
| E — XGBoost (SMOTE) | 0.4990 | **0.9710** | 0.0042 | 7.0 ms | 34 s |
| F — Isolation Forest | 0.0319 | 0.8676 | 0.0918 | 28 ms | 2 s |

**Bold = best in column.**

### 10.4 What these results mean

**XGBoost with class weighting (D) is selected**, on three independent grounds:

- **Best PR-AUC (0.5203).** Under 1:774 imbalance, PR-AUC is the metric that does not flatter a model. ROC-AUC
  rewards ranking quality; PR-AUC rewards actually finding the fraud. For a fraud system, only the second matters.
- **Real-time capable.** 7.2 ms median latency. Random Forest at 110 ms is 15× slower for *worse* PR-AUC.
- **Well calibrated enough to be useful.** A Brier score of 0.0358 is high relative to the others, which is
  expected: class weighting deliberately trades probability calibration for recall. The scores remain useful for
  *ranking*, and ranking is what a threshold needs.

**The honest counter-argument** is model E (SMOTE), which has the best ROC-AUC (0.9710) and a much better Brier
score (0.0042). It was not selected because PR-AUC is the operationally decisive metric here, and because
oversampling can teach the model about *synthetic* fraud patterns that do not generalise. Both facts are
recorded rather than hidden.

**Isolation Forest (F) scored poorly as a classifier (PR-AUC 0.0319) — and this is expected, not a failure.** It
is unsupervised: it was never told what fraud looks like, so it flags *unusual* transactions, of which fraud is
only one cause. This is precisely why it is used in the hybrid engine as a **supporting risk signal with a small
weight**, not as the primary detector. Its own result file states this explicitly: *"Anomaly score is an
additional risk signal, not a fraud classifier."*

### 10.5 Operating points

Each model is reported at four operating modes, because "the best model" is incomplete without saying *where on
the precision–recall curve you are running*:

| Mode | Objective |
|------|-----------|
| `high_recall` | Catch as much fraud as possible; accept false alarms |
| `high_precision` | Almost every alert is real; accept missing fraud |
| `balanced` | Compromise |
| `min_cost` | Minimise expected cost under the cost matrix (5 per FP, 500 per FN) |

For model D (XGBoost balanced), at `min_cost` the validation threshold of 0.85 yields recall **0.737** — catching
about three quarters of all fraud — at a threshold that the *validation* set, not the test set, selected.

### 10.6 A note on deceptive accuracy

A model that always answers "legitimate" scores **99.87% accuracy** on this dataset while detecting **zero** fraud.
This single observation is why the project reports PR-AUC, recall and cost rather than accuracy, and why §11 uses a
multi-signal score instead of a bare classifier output.

---

## 11. The Hybrid Risk Engine

The deployed model is not one classifier. It is a **weighted combination of four independent signals**, because
each signal catches fraud the others miss.

### 11.1 The four signals

| Signal | Range | Source | What it uniquely catches |
|--------|-------|--------|--------------------------|
| **ML** | 0–1 | XGBoost probability | Statistical patterns in combinations no human would enumerate |
| **Anomaly** | 0–1 | Isolation Forest | Transactions unlike *this user's* norm, even if common globally |
| **Behaviour** | 0–1 | Deterministic formula | Deviation from the account's own baseline |
| **Rules** | 0–1 | 7 deterministic rules | Known attack patterns with unambiguous physics |

### 11.2 The aggregation formula

```text
FinalRisk = 100 × Σ(wᵢ × sᵢ) / Σ(wᵢ)      over the signals AVAILABLE for this transaction
```

where each `sᵢ ∈ [0,1]` is a signal value and each `wᵢ` is its weight.

**Critical design detail — missing signals are excluded, not zeroed.** If a signal is unavailable (no anomaly
model loaded, or a feature is `NaN`), it is *left out* and the remaining weights are **renormalised**. Treating a
missing signal as `0` would silently drag a score toward "safe" precisely when the system knows least — the most
dangerous possible failure direction for a fraud system. This is a safety decision, not a convenience.

### 11.3 The seven deterministic rules

These fire on unambiguous, explainable conditions:

| Rule | Condition | Points |
|------|-----------|--------|
| `impossible_velocity` | Implied speed > 900 km/h between consecutive transactions | 0.9 |
| `new_device_and_location_change` | New device **and** new location simultaneously | 0.6 |
| `card_testing` | ≥3 transactions within 5 minutes, each small relative to the user's average | 0.6 |
| `extreme_amount_deviation` | Amount ≥ 8× the user's mean, or z-score ≥ 4 (requires ≥5 prior transactions) | 0.5 |
| `transaction_burst` | ≥5 in 1 minute, or ≥15 in 1 hour | 0.5 |
| `suspicious_counterparty` | Counterparty's confirmed-fraud rate ≥ 5% | 0.5 |
| `unusual_hour_high_amount` | High amount (≥3× average) at an hour rare for the user | 0.3 |

Rule points are summed and capped at 1.0. Several rules require a **minimum history** (5 transactions) — judging a
new account against a baseline of one transaction would manufacture false alarms.

`impossible_velocity` is also configured as a **force-review rule**: it escalates to REVIEW regardless of the
total score, because a physically impossible journey is not negotiable evidence.

### 11.4 The behavioural score

```text
confidence = min(1, prior_transactions / 5)
```

The behavioural score is a weighted sum of baseline deviations, each scaled by `confidence`:

| Component | Internal weight |
|-----------|----------------|
| log-scaled amount ratio | 0.30 |
| amount z-score / 5 | 0.20 |
| 5-minute velocity / 5 | 0.15 |
| new device | 0.15 |
| location change | 0.15 |
| unusual hour | 0.05 |

A new-device signal is discounted (×0.3) when the user has *no* prior devices — a first-ever device is normal, a
*second* unfamiliar device is not.

### 11.5 From score to action

| Score | Risk level | Decision |
|-------|-----------|----------|
| 0–29 | LOW | ALLOW |
| 30–59 | MEDIUM | REVIEW (or ALLOW if below review threshold) |
| 60–79 | HIGH | REVIEW / BLOCK by threshold |
| 80–100 | CRITICAL | BLOCK (at/above block threshold) |

Review and block thresholds are themselves **tuned on validation data**, not hand-picked. The live configuration
uses a review threshold of 5.0 and a block threshold of 95.0 — deliberately wide, because the two thresholds serve
different purposes: *review* catches suspicious activity for a human, *block* should fire only with high
confidence.

### 11.6 Live model configuration and an honest observation

The trained live model (`live-hybrid-v1`) was tuned on 60,000 synthetic behavioural rows and produced:

| Property | Value |
|----------|-------|
| PR-AUC | 0.6038 |
| ROC-AUC | 0.9393 |
| Review mode | precision 0.184, recall 0.915, F1 0.307 @ threshold 0.05 |
| Block mode | precision 0.926, recall 0.177, F1 0.298 @ threshold 0.95 |
| `scale_pos_weight` | 77.09 |

**Tuned signal weights: `ml` = 0.9, `behavior` = 0.1, `anomaly` = 0.0, `rules` = 0.0.**

This is worth stating plainly rather than hiding: **the validation-based tuner assigned zero weight to the
anomaly and rule signals.** On this synthetic training distribution, the supervised model alone was the most
informative combination, and the tuner — optimising the stated objective — correctly concluded the other signals
added nothing *on that data*.

The practical consequence is that in the current configuration, the deterministic rules contribute to the
**human-readable reasons and the alert narrative** but not numerically to the score. This is a real finding about
the tuning data, and it is reported as such. Two defensible readings exist, and the project does not pretend to
settle it: either the synthetic training distribution does not contain the rule-triggering patterns in sufficient
quantity, or the tuner's objective did not reward complementary coverage. Resolving it requires training data
with verified attack scenarios, which is future work (§22).

The two operating modes remain useful and complementary: the *review* threshold catches 91.5% of fraud for
human review, while the *block* threshold is 92.6% precise — a system that blocks only what it is confident about.

---

## 12. Backend API Reference

The system exposes **44 API operations** under the `/api/v1` prefix, generated from the live OpenAPI schema.
Interactive documentation is served at `/docs`.

### 12.1 Authentication

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/auth/register` | Create an account |
| POST | `/api/v1/auth/login` | Authenticate; returns a JWT |
| GET | `/api/v1/auth/me` | Current user's identity and role |

### 12.2 Transactions and scoring

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/api/v1/transactions/predict` | **Score a transaction** — the core endpoint |
| GET | `/api/v1/transactions` | List transactions (paginated) |
| GET | `/api/v1/transactions/{id}/detail` | Full transaction, prediction and explanation |
| PATCH | `/api/v1/transactions/{id}/action` | Analyst decision (allow / block) |

### 12.3 Alerts and cases

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/alerts` | List fraud alerts |
| PATCH | `/api/v1/alerts/{id}` | Update alert status / resolve |
| GET | `/api/v1/cases` | List investigation cases |
| POST | `/api/v1/cases` | Create a case |
| GET | `/api/v1/cases/{id}` | Case detail |
| PATCH | `/api/v1/cases/{id}` | Update case status / priority |
| POST | `/api/v1/cases/{id}/notes` | Add an analyst note |

### 12.4 Dashboard analytics

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/dashboard/kpis` | Headline KPIs — **live traffic only** |
| GET | `/api/v1/dashboard/trends` | Volume over time — **live scope** |
| GET | `/api/v1/dashboard/corpus-trends` | Training-corpus series, explicitly separate |
| GET | `/api/v1/dashboard/risk-distribution` | Count per risk level — live only |
| GET | `/api/v1/dashboard/geographic` | Transactions by location — live only |
| GET | `/api/v1/dashboard/device-activity` | Activity by device type |
| GET | `/api/v1/dashboard/merchant-risk` | Highest-risk merchants |
| GET | `/api/v1/dashboard/model-info` | Active model version and metrics |
| GET | `/api/v1/dashboard/paysim-by-type` | Ground-truth fraud by PaySim type |

### 12.5 Monitoring and model governance

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/monitoring/live-feed` | Live feed status: running, generated, errors |
| GET | `/api/v1/monitoring/drift` | Current PSI drift measurement |
| GET | `/api/v1/monitoring/history` | Drift history over time |
| GET | `/api/v1/monitoring/models` | Model registry |
| POST | `/api/v1/monitoring/models/{id}/activate` | Activate a registered model version |
| GET | `/api/v1/monitoring/security` | Security control test matrix |

### 12.6 Administration

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/users` | List users (admin only) |
| POST | `/api/v1/users` | Create a user with a role (admin only) |
| PATCH | `/api/v1/users/{id}/role` | Change a user's role (admin only) |
| DELETE | `/api/v1/users/{id}` | Delete a user (admin only) |
| GET | `/api/v1/audit` | Audit log with filters and pagination |
| GET | `/api/v1/reports/export` | Export a report |

### 12.7 Profiles, merchants, feedback and graph

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/v1/profiles` | Top behavioural profiles |
| GET | `/api/v1/profiles/{user_id}` | One user's behavioural profile |
| GET | `/api/v1/merchants` | Merchant risk list |
| GET | `/api/v1/merchants/{id}` | One merchant |
| GET | `/api/v1/feedback` | Recorded analyst feedback |
| POST | `/api/v1/feedback` | Record confirmed-fraud / false-positive |
| POST | `/api/v1/feedback/retraining-manifest` | Build a retraining manifest |
| GET | `/api/v1/graph/risk` | Network risk across user / device / merchant |

### 12.8 Health

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Liveness check |

### 12.9 Error format

Every error uses one consistent shape, and **stack traces are never leaked**:

```json
{ "error": { "code": "EMAIL_EXISTS", "message": "Email already registered" } }
```

---

## 13. Database Design

**14 tables** model users, transactions, predictions, alerts, cases, notes, feedback, merchants, behaviour,
model governance and auditing. Plus one pre-aggregated rollup table for performance.

### 13.1 Table reference

| # | Table | Columns | Purpose |
|---|-------|---------|---------|
| 1 | `users` | 5 | Accounts, bcrypt hash, role |
| 2 | `transactions` | 11 | Every scored transaction, live and corpus |
| 3 | `devices` | 5 | Device fingerprint per user; first-seen time |
| 4 | `fraud_predictions` | 16 | Score, level, decision, explanation, per-signal breakdown |
| 5 | `fraud_alerts` | 7 | Alert severity, status, resolution |
| 6 | `fraud_cases` | 10 | Investigation case, priority, assignment, closure |
| 7 | `case_notes` | 5 | Analyst notes on a case |
| 8 | `fraud_feedback` | 8 | Confirmed fraud / false positive, with feature snapshot |
| 9 | `audit_logs` | 8 | Every admin action and every login attempt |
| 10 | `merchants` | 5 | Merchant and category risk |
| 11 | `user_behavior_profiles` | 12 | Rolling behavioural summary per user |
| 12 | `model_versions` | 14 | Model registry: metrics, activation, artefact path |
| 13 | `drift_snapshots` | 6 | PSI measurements over time |
| 14 | `security_events` | 5 | Security control test results |
| — | `paysim_rollup_hourly` | — | Pre-aggregated hourly corpus totals (performance) |

### 13.2 Column detail for the core tables

**`transactions`** — `id`, `user_id`, `merchant_id`, `device_id`, `amount`, `currency`, `location`,
`ip_address`, `payment_method`, `status`, `created_at`

`status` is `allowed` or `flagged`. The identifier's *sign* carries meaning: negative = training corpus,
non-negative = live traffic.

**`fraud_predictions`** — `id`, `transaction_id`, `probability`, `risk_score`, `risk_level`, `model_version`,
`explanation`, `decision`, `anomaly_score`, `behavior_score`, `rule_score`, `triggered_rules`, `reasons`,
`signal_contributions`, `weights_used`, `created_at`

Storing the **individual signal scores, the triggered rules, the per-signal contributions and the weights
actually used** is what makes a historical decision auditable months later. Because the exact inputs to every
past score are persisted, any decision can be reconstructed and explained — including which model version and
which weight configuration produced it.

**`audit_logs`** — `id`, `user_id`, `action`, `target_type`, `target_id`, `detail`, `ip_address`, `created_at`

The `detail` column was added by migration `c3d81f4a2b90` so an entry can explain itself, e.g.
`analyst -> user` for a role change, or `wrong password for verify@fraudshield.ai` for a failed login.

### 13.3 Referential integrity

- `fraud_predictions.transaction_id` → `transactions.id` (unique — one prediction per transaction)
- `fraud_alerts.transaction_id` → `transactions.id`
- `fraud_cases.alert_id` → `fraud_alerts.id`
- `case_notes.case_id` → `fraud_cases.id`
- `fraud_feedback.prediction_id` / `.case_id` → their parent tables
- `transactions.user_id` → `users.id`; `transactions.device_id` → `devices.id`

The test suite asserts **zero orphaned prediction rows**, so a prediction can never exist without its
transaction.

### 13.4 Migrations

| Revision | Description |
|----------|-------------|
| `4af2b79611aa` | Initial schema — users, merchants, devices |
| `9b2c7e4a1f20` | Major project upgrade |
| `7c9e4d2f3a11` | Hybrid prediction fields |
| `c3d81f4a2b90` | `audit_logs.detail` column |

---

## 14. Frontend Dashboard

Eight pages, built with React 19, Tailwind CSS v4 and Recharts.

| Page | Route | Purpose |
|------|-------|---------|
| **Login** | `/login` | Authentication; failure shows a clear message |
| **Dashboard** | `/dashboard` | KPIs, live trend chart, risk distribution, geographic view, live feed panel, separate corpus panel |
| **Alerts** | `/alerts` | Fraud alert queue with severity and status |
| **Transaction Detail** | `/transactions/:id` | Full scoring breakdown and SHAP explanation |
| **Cases** | `/cases` | Investigation management with notes |
| **Audit Log** | `/audit` | Administrator action trail with filters |
| **Users** | `/users` | Create users, assign roles, delete accounts |
| **Intelligence** | `/intelligence` | Drift, model registry, security matrix, profiles |

### 14.1 Dashboard design decisions

**The dashboard shows live traffic only.** KPI cards, the trend chart, the risk distribution and the geographic
view are all scoped to live transactions. The training corpus is displayed in a separate, clearly-labelled panel
reading *"Training corpus (PaySim) — not live volume"*, with a note that it is excluded from the KPIs above.

**The trend chart is hourly and starts empty.** On a freshly reset system it reads *"Waiting for the first live
transactions…"* and fills in as the feed runs. A chart pre-populated with six months of historical data would
hide the fact that nothing is actually happening right now.

**The live feed panel always renders.** When no event has arrived it states *"Live feed connected — waiting for
the next transaction."* — distinguishing "connected but idle" from "broken", which an empty panel cannot convey.

**The feed status is visible.** A banner reports whether the feed is running, so a stalled feed is immediately
diagnosable rather than silently showing stale numbers.

### 14.2 Resilience

The Intelligence page loads five independent panels using `Promise.allSettled` rather than `Promise.all`. With
`Promise.all`, a single failing request discards **every** successful result and the whole page renders empty.
With `Promise.allSettled`, each panel renders independently — one unavailable endpoint cannot blank the page.

### 14.3 Audit page

The audit view is built for an investigator's actual questions:

- **Actor** shown as an email address, not a raw numeric id
- **Target** resolved to a human label (`user verify@fraudshield.ai`)
- **Detail** explaining the event in plain language
- **Failed logins highlighted in red** — these are the rows an investigator is looking for
- **"Auth events only" toggle** and a per-action dropdown
- Pagination with the true page size

---

## 15. Real-Time Architecture

### 15.1 Two mechanisms, one purpose

| Mechanism | Used for | Why |
|-----------|----------|-----|
| **Built-in live feed** | Continuously generating demo traffic | The dashboard is never empty; no external process needed |
| **WebSocket (Socket.IO)** | Pushing results to dashboards | Sub-second updates without polling |

### 15.2 The built-in live feed

A background task inside the FastAPI process generates synthetic traffic and pushes it through
`ingest_transaction()` — **the same function the HTTP endpoint calls**. This is enforced structurally rather
than by convention: there is one pipeline, and both callers invoke it.

> **Why this matters.** When the feed was a separate simulator making HTTP requests, the pipeline existed in two
> places. Any change had to be made twice, and the dashboard silently diverged from what the endpoint actually
> did. Extracting the pipeline into a single shared function removed that entire class of bug.

**Configuration** (environment variables):

| Setting | Default | Meaning |
|---------|---------|---------|
| `LIVE_FEED_ENABLED` | `true` | Start the feed on application startup |
| `LIVE_FEED_INTERVAL_SECONDS` | `5.0` | Delay between bursts |
| `LIVE_FEED_BURST` | `3` | Transactions per burst → 3 per 5 s = 0.6/s |

**Ten fraud scenarios** are generated, weighted to give a realistic spread: `normal` (40), `suspicious` (15),
`high_value` (10), `rapid_repeated` (8), `new_device` (8), `unusual_location` (6), `card_testing` (4),
`account_takeover` (4), `transaction_splitting` (3), `fraud_ring` (2).

**Error isolation.** A failing transaction increments an error counter and the feed **continues**. It is never
allowed to die — otherwise one transient database error would silently freeze the dashboard for the rest of the
session. `GET /monitoring/live-feed` exposes `running`, `generated`, `errors` and `last_error` so the failure
would be visible rather than silent.

**The feed starts in the application lifespan**, so a signed-in dashboard always has traffic. It can be disabled
with `LIVE_FEED_ENABLED=false` — which is exactly what the automated test suite does, to keep tests deterministic.

### 15.3 Verified behaviour

| Property | Verified |
|----------|----------|
| Total starts at exactly 0 on a clean reset | ✅ |
| Total increases automatically with no user action | ✅ (observed 495 → 501 over 12 s) |
| Live ids are contiguous from 0 | ✅ |
| Corpus never appears in live counts | ✅ |
| Feed survives individual transaction failures | ✅ (unit-tested) |
| Feed errors remain 0 under sustained running | ✅ |

---

## 16. Security Controls

| Control | Implementation | Status |
|---------|---------------|--------|
| Password hashing | bcrypt via passlib — never plaintext | Implemented |
| Token authentication | JWT, HS256, 60-minute expiry, secret from environment | Implemented |
| Access control | `require_role([...])` dependency, applied per route | Implemented |
| Input validation | Pydantic schemas on every request body | Implemented |
| SQL injection prevention | SQLAlchemy ORM — parameterised queries only | Implemented |
| CORS | Explicit allow-list, never `"*"` | Implemented |
| Rate limiting | slowapi: login 10/min, prediction 60/min | Implemented |
| Error handling | Consistent `{"error": {...}}` shape; no stack traces leaked | Implemented |
| Structured logging | Method, path, status, latency; no passwords or full tokens | Implemented |
| Audit trail | Every admin action, every login attempt | Implemented |
| Secrets management | `.env` gitignored; `.env.example` holds placeholders only | Implemented |
| HTTPS | Enforced by the hosting platform in deployment | Deployment-time |

### 16.1 Verified by automated tests

| Attack / condition | Expected | Verified |
|--------------------|----------|----------|
| No token supplied | 401 | ✅ |
| Invalid / tampered JWT | 401 | ✅ |
| Correct token, wrong role (admin-only route) | 403 | ✅ |
| Correct token, wrong role (analyst route) | 403 | ✅ |
| SQL-injection string in `amount` | 422 (rejected before reaching SQL) | ✅ |
| Negative amount | 422 | ✅ |
| Rate limit exceeded | 429 | ✅ |
| Duplicate user email | 409 `EMAIL_EXISTS` | ✅ |
| Password present in audit records | Never stored | ✅ |

The SQL-injection test is worth emphasising: the malicious string is rejected by **Pydantic validation before it
can reach the database layer at all**. Defence is structural, not a filter that might be bypassed.

### 16.2 Never stored, anywhere

Real card numbers, CVVs, OTPs, merchant credentials and banking details appear **nowhere** — not in the code,
not in the datasets, not in the test fixtures, not in the simulator. Passwords are stored only as bcrypt hashes,
and a test asserts that no submitted password string ever appears in an audit record.

---

## 17. Audit Trail and Accountability

### 17.1 What is recorded

| Event | Recorded detail |
|-------|-----------------|
| `auth.login` | Actor, resolved user target, `role=<role>`, IP, timestamp |
| `auth.login_failed` | Attempted email, reason (`wrong password for …` / `unknown email: …`), IP |
| `user.create` | Email created and the role assigned |
| `user.update_role` | Explicit `analyst -> user` transition |
| `user.delete` | Which account was removed |

### 17.2 Failed logins are recorded

Recording only *successful* logins leaves the most security-relevant gap: you cannot detect credential
brute-forcing if failed attempts are discarded. Both failure modes are captured and distinguished:

- **Wrong password for a known account** — the account is identified as the target, which is the signature of a
  brute-force attempt against a specific user.
- **Unknown email** — a different attack pattern: credential stuffing or address enumeration.

### 17.3 Human-readable entries

An audit log that stores only `user_id: 2, action: update` is technically complete and practically useless.
Entries are resolved to a human label and a plain-language detail:

| Before | After |
|--------|-------|
| `user_id: 2, action: auth.login` | `verify@fraudshield.ai — auth.login — user verify@fraudshield.ai — role=admin` |
| `action: user.update_role` | `persist-…@fraudshield.ai: analyst -> user` |

### 17.4 A deliberate non-action

Audit rows written **before** the `detail` column existed are left exactly as they were. They are not
back-filled with invented values, because a reconstructed audit entry is no longer evidence. This is stated
explicitly and covered by a test asserting that legacy rows are not retroactively rewritten.

### 17.5 No credentials in the audit log

A dedicated test submits a distinctive password and asserts that the string appears nowhere in the audit
response. This is a regression guard, not a one-time check.

---

## 18. Testing Strategy and Results

### 18.1 Totals

| Suite | Tests | Result |
|-------|-------|--------|
| Backend (pytest) | **46** | All passing |
| Machine learning (pytest) | **49** | All passing |
| **Total** | **95** | **All passing** |

### 18.2 Backend coverage by file

| File | Tests | Focus |
|------|-------|-------|
| `test_live_feed.py` | 16 | Feed scoring, resilience, live-only scoping, audit, user persistence |
| `test_rbac_and_security.py` | 8 | Authentication, authorisation, injection, rate limiting |
| `test_auth.py` | 7 | Login, registration, token handling |
| `test_transactions_integration.py` | 7 | End-to-end prediction, live id allocation |
| `test_decision_engine_unit.py` | 6 | Risk levels, thresholds, rule logic |
| `test_hybrid_integration.py` | 2 | Hybrid scoring integration |

### 18.3 A real bug the tests found

The test suite uncovered a genuine defect during development: the application lifespan was starting the live feed
**inside the test run**, where the background writer wrote to a *different* in-memory database than the one under
test. This made every count-based assertion non-deterministic — tests could pass or fail depending on timing.

Fixed by setting `LIVE_FEED_ENABLED=false` in `conftest.py` and covering feed behaviour explicitly in
`test_live_feed.py`. This is precisely the class of bug a test suite exists to find: not a crash, but a silent
loss of trustworthiness in the results.

### 18.4 Test isolation

Tests use **in-memory SQLite** with a static connection pool, so the suite needs no external database and runs in
under a minute. SQLAlchemy's dependency override swaps the real session for the test session. Rate-limit buckets
are reset between tests.

### 18.5 What is verified end-to-end

| Behaviour | Verification |
|-----------|-------------|
| A clean system reports 0 total transactions | Automated test |
| Live transactions count upward | Automated test |
| A corpus row never enters live KPIs | Automated test |
| Risk and geographic panels sum to the live total | Automated test |
| Trends report live scope; corpus trends stay separate | Automated test |
| A feed transaction produces a real prediction | Automated test |
| The feed survives a failing transaction | Automated test |
| Successful and failed logins are both audited | Automated test |
| Passwords never appear in audit records | Automated test |
| Created users persist and can log in | Automated test |
| Role changes persist and take effect | Automated test |
| The dashboard count rises with no interaction | **Live browser verification** |
| Failed logins are highlighted in the UI | **Live browser verification** |
| Frontend compiles with no errors | `npm run build` ✅ |

---

## 19. How to Run the System

### 19.1 Prerequisites

Python 3.11+, Node.js 18+, and either PostgreSQL 16 or SQLite (bundled).

### 19.2 Backend

```bash
cd backend
pip install -r requirements.txt

# environment
#   DATABASE_URL=postgresql://user:pass@localhost:5432/fraudshield
#   JWT_SECRET=<a long random string>
#   LIVE_FEED_ENABLED=true          # built-in live feed on

alembic upgrade head               # apply database migrations
uvicorn app.main:app --reload      # start the API
```

| Service | URL |
|---------|-----|
| API | http://127.0.0.1:8000 |
| Interactive API docs | http://127.0.0.1:8000/docs |
| Health check | http://127.0.0.1:8000/health |

### 19.3 Frontend

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and sign in.

### 19.4 Live feed configuration

The feed starts automatically. To change its pace:

| Variable | Effect |
|----------|--------|
| `LIVE_FEED_INTERVAL_SECONDS=2` | Twice as fast |
| `LIVE_FEED_BURST=10` | Ten per burst |
| `LIVE_FEED_ENABLED=false` | Disable entirely (also what the test suite does) |
| `GET /api/v1/monitoring/live-feed` | Inspect current status |

### 19.5 Running the tests

```bash
cd backend && pytest -q            # 46 tests
cd ml/src   && pytest -q           # 49 tests
cd frontend && npm run build       # compile check
```

---

## 20. Results Summary

### 20.1 Machine learning (PaySim test split, 1,293,523 rows / 4,258 fraud)

| Metric | Best value | Model |
|--------|-----------|-------|
| **PR-AUC** (primary metric) | **0.5203** | XGBoost + class weighting |
| ROC-AUC | 0.9710 | XGBoost + SMOTE |
| F1 (balanced mode, XGBoost CW) | 0.4725 | Random Forest balanced |
| Recall (min-cost mode, XGBoost CW) | 0.737 | XGBoost + class weighting |
| Precision (block mode) | 0.926 | XGBoost + class weighting |
| Inference latency | 7.2 ms median | XGBoost + class weighting |

### 20.2 Dataset

6,362,620 transactions · 8,213 fraud · 0.1291% fraud rate · zero missing values · zero duplicates.

### 20.3 Engineering

| Measure | Value |
|---------|-------|
| Automated tests | **95 passing** (46 backend + 49 ML) |
| API operations | 44 |
| Database tables | 14 (+1 rollup) |
| Frontend pages | 8 |
| Live features per transaction | 26 |
| Deterministic fraud rules | 7 |
| Model variants evaluated | 8 |
| Dashboard count growth, unattended | Verified (495 → 501 in 12 s) |
| Frontend build | Clean |
| Browser console errors | 0 |

### 20.4 What the system demonstrably does

1. Scores a transaction against 26 point-in-time behavioural features in **~7 ms**.
2. Explains each decision in plain language, with per-feature attribution.
3. Catches fraud that is only visible as a *combination* of weak signals.
4. Catches impossible travel by pure geometry, with no training data at all.
5. Starts from a genuinely empty state and fills up live, with no manual step.
6. Enforces role-based access control on every route and records every admin action.
7. Records failed logins, so brute-force attempts are visible after the fact.
8. Remains honest: the corpus is excluded from live KPIs and labelled separately.

---

## 21. Limitations and Honest Caveats

A report that lists only strengths is not credible. These are the real constraints.

### 21.1 Data limitations

| # | Limitation | Consequence |
|---|-----------|-------------|
| L1 | PaySim is **synthetic** | Results describe the simulation, not real fraud. Absolute metrics will not transfer to production. |
| L2 | Fraud appears in only 2 of 5 transaction types | A model trained on this data could learn "only CASH_OUT and TRANSFER are risky" — a false rule that would be actively harmful in production. |
| L3 | Maximum 3 transactions per user | Behavioural features (velocity, baseline deviation) are **weakly supported** — there is very little history to learn from. This is the single biggest dataset limitation. |
| L4 | 0.146% of users have more than one transaction | Repeat-offender and escalation patterns cannot be studied. |
| L5 | Test fraud rate (0.329%) is 4× the training rate (0.084%) | Chronological variation, not a bug — but it means the model is selected in a calm regime and tested in a turbulent one. |
| L6 | 24-hour label delay | Models must be trained without labels that do not yet exist; a small amount of the most recent data is unusable. |

### 21.2 Model limitations

| # | Limitation | Consequence |
|---|-----------|-------------|
| L7 | Tuner assigned **zero weight** to anomaly and rule signals | In the current configuration the deterministic rules inform the *explanation* but not the score. See §11.6. |
| L8 | Best PR-AUC is 0.52, not near-perfect | Roughly half of all fraud is still missed at any single threshold. This is realistic for this class of problem, but it must not be glossed over. |
| L9 | The live model is trained on **synthetic** behavioural data | Its feature relationships are only as valid as the generator that produced them. |
| L10 | Rule weights were hand-specified as *points* | Rule *thresholds* are documented constants; only the signal *weights* were tuned on validation data. |
| L11 | Class weighting degrades probability calibration (Brier 0.0358 vs 0.0042 for SMOTE) | Scores are reliable for *ranking* but should not be quoted as calibrated probabilities. |

### 21.3 System limitations

| # | Limitation | Consequence |
|---|-----------|-------------|
| L12 | Hard browser refresh clears the session | The JWT is held in memory, so a refresh returns the user to the login screen. Not fixed — out of scope for the last change set. |
| L13 | No HTTPS in local development | Tokens travel in cleartext locally. Production deployment provides TLS. |
| L14 | Single-process background feed | The feed runs in the application process; running multiple workers would produce multiple feeds. |
| L15 | In-memory rate-limit state | Rate limits reset on restart and are not shared across processes. |
| L16 | `/merchants` is empty in the demo database | No merchant records exist, so merchant analytics have nothing to show. |
| L17 | No pagination on some list endpoints | Large result sets could be slow at scale. |

### 21.4 The most important limitation

**This system has never seen real fraud.** Every number in §20 comes from a public synthetic dataset or from
synthetic traffic. Public-dataset metrics do not establish production banking performance. A real deployment
would require real (properly anonymised and legally obtained) labelled data, adversarial evaluation, regulatory
sign-off, and — above all — a much longer evaluation period.

---

## 22. Future Work

| # | Proposed work | Why it matters |
|---|--------------|----------------|
| F1 | Acquire a dataset with genuine repeat behaviour (multiple transactions per user) | Directly addresses L3 — the largest constraint on the behavioural features |
| F2 | Retrain with attack scenarios present, then re-tune | Tests whether the rules earn non-zero weight, resolving the §11.6 question empirically |
| F3 | Persist the JWT in `httpOnly` cookies | Fixes L12; also reduces token exposure to client-side script |
| F4 | Move to `pgvector` or a graph store for network risk | Makes the graph endpoint genuinely useful for fraud-ring detection |
| F5 | Automated retraining on feedback, with champion/challenger evaluation | Closes the feedback loop rather than only recording it |
| F6 | Alert on PSI drift to trigger automatic review | Makes drift monitoring operational |
| F7 | Per-tenant isolation and a real permission matrix | Required for any multi-user deployment |
| F8 | Full PCI-DSS-aligned handling of real card data | The only path from prototype to production — and a multi-year effort |
| F9 | Load testing and horizontal scaling | The feed must become a proper queue consumer beyond a single process |
| F10 | Explainability reviewed with real analysts | Ensure explanations match how fraud investigators actually reason |

---

## 23. Conclusion

FraudShield AI delivers a complete, working and honestly-evaluated fraud-detection system.

**Technically**, the project achieves its objectives: a leak-free benchmark on 6.36 million real public-dataset
transactions, eight model variants compared under a strict protocol, a selected model at 0.5203 PR-AUC with
7.2 ms inference, a hybrid risk engine combining four independent signals, 44 API operations across 14 database
tables, an 8-page real-time dashboard, and 95 passing automated tests.

**The most defensible engineering decisions** are architectural, not flashy:

- **A single shared pipeline.** The HTTP endpoint and the live feed invoke the same function, so the dashboard
  cannot silently diverge from the API. This eliminated a whole category of bug.
- **Strict live/corpus separation.** Training data is never counted as operational activity, so the headline
  numbers mean what they claim to mean.
- **Point-in-time feature construction**, enforced structurally by computing features *before* persisting the
  row — so a transaction can never contribute to its own history.
- **Multi-signal scoring**, because each signal catches fraud the others miss.
- **Recording failed logins**, because discarding them makes brute-force attacks invisible.
- **Reporting the tuner's zero weights rather than hiding them**, even though it complicates the story.

**The honest conclusion is also a limit.** The strongest result here is PR-AUC 0.52 — meaning at any single
threshold the system misses roughly half of all fraud. That is realistic for this class of problem, but it is the
number that should govern any claim about the system's usefulness. Combined with a dataset in which users have at
most three transactions, the behavioural features — the most human-interpretable part of the design — are the
weakest-supported component, and no amount of model tuning can fix that; only better data can.

What the project does establish is the **complete path** from raw data to a defensible real-time decision with an
audit trail, and the engineering discipline to know which parts of that path are strong and which are not.

---

## Appendix A — Complete File Map

### Backend (`backend/`)

```text
app/
├── main.py                     Application setup, lifespan, router registration
├── config/settings.py          Environment-driven configuration
├── database/session.py         Engine, session factory
├── auth/
│   ├── security.py             bcrypt hashing, JWT creation
│   └── dependencies.py         get_current_user, require_role
├── models/                     14 SQLAlchemy ORM models
├── schemas/                    Pydantic request/response validation
├── routes/                     13 routers → 44 operations
├── services/
│   ├── prediction_pipeline.py  ★ Single source of truth for scoring
│   ├── feature_engineering.py  Point-in-time feature computation
│   ├── live_feed.py            ★ Built-in synthetic feed
│   └── audit_service.py        Audit recording
├── ml/model_service.py         Model loading, SHAP explanation, prediction
├── utils/                      Error handlers, logging, rate limiting
└── websocket/socket_server.py  Real-time event emission
alembic/versions/               4 schema migrations
tests/                          46 tests
```

★ = central to the live feed and scoring work

### Machine learning (`ml/`)

```text
src/
├── fraudpipe/
│   ├── features.py             Feature construction
│   ├── preprocess.py           Cleaning and imputation
│   ├── split.py                Chronological time-aware splitting
│   ├── experiments.py          Model comparison harness
│   ├── metrics.py              PR-AUC, ROC-AUC, cost
│   ├── tune.py                 Threshold and weight tuning on validation
│   ├── risk_engine.py          ★ Hybrid 4-signal risk engine
│   └── build_dataset.py        PaySim dataset construction
├── train_live_model.py         Trains the deployed live-hybrid-v1 model
├── decision_engine.py          Decision logic
└── test_*.py                   49 tests
models/
├── live-v1/                    ★ Deployed artefacts
│   ├── metadata.json           Version, metrics, feature list, tuned weights
│   ├── preprocessor.json       Feature order + imputation medians
│   ├── risk_config.json        Tuned weights and thresholds
│   ├── supervised.joblib       XGBoost model
│   └── isolation_forest.joblib Anomaly model
└── experiments/paysim-v1/
    └── experiment_results.json ★ Full 8-model benchmark
```

### Frontend (`frontend/`)

```text
src/
├── App.jsx, main.jsx           Application shell and routing
├── pages/
│   ├── Login.jsx
│   ├── Dashboard.jsx           ★ Live KPIs, trends, corpus panel
│   ├── Alerts.jsx
│   ├── Cases.jsx
│   ├── TransactionDetail.jsx
│   ├── AuditLog.jsx            ★ Actor, target, detail, filters
│   ├── Users.jsx
│   └── Intelligence.jsx
├── components/                 KpiCard, NavBar, ProtectedRoute, RiskBadge
├── context/AuthContext.jsx     JWT + role state
└── services/
    ├── api.js                  Axios instance with auth interceptor
    └── socket.js               WebSocket client
```

### Other

| Path | Contents |
|------|----------|
| `scripts/simulator.py` | Standalone transaction generator (optional; the built-in feed supersedes it) |
| `docs/` | 30+ supporting documents: architecture, security, testing, deployment, viva preparation |
| `ml/data/processed/paysim-v1/` | Dataset card, metadata, feature schema |

---

## Appendix B — One-Page Quick Reference

**The problem.** Card fraud is rare (1 in 774) but arrives in patterns, and missing it is far more costly than
over-flagging it. Batch scoring detects too late and remembers nothing.

**The data.** PaySim, 6,362,620 transactions, 8,213 fraud (0.1291%), 742 hours, zero missing values, zero
duplicates, SHA-256 recorded for verification.

**The leak prevention.** Post-balance columns dropped (they encode the outcome), `isFlaggedFraud` dropped (it
encodes the label), behavioural features strictly point-in-time, test set touched exactly once.

**The models.** 8 variants: logistic regression, random forest, XGBoost (each plain, class-weighted, and
XGBoost + SMOTE), plus unsupervised Isolation Forest.

**The winner.** XGBoost + class weighting — **PR-AUC 0.5203**, ROC-AUC 0.9665, 7.2 ms inference.

**The deployed system.** 4 signals (ML 0.9, behaviour 0.1, anomaly 0.0, rules 0.0 as tuned) → 0–100 score →
LOW/MEDIUM/HIGH/CRITICAL → ALLOW/REVIEW/BLOCK. 26 features, 7 deterministic rules, thresholds tuned on validation.

**Why hybrid.** The best classifier is only 0.52 PR-AUC. A single signal cannot be trusted; impossible-travel
geometry catches takeover with no training data at all.

**The engineering.** 44 API operations · 14 tables · 8 pages · 95 tests (46 + 49) · 0 console errors · 0 feed
errors · live count verified rising unattended.

**The honesty.** All data is public or synthetic. Users have at most 3 transactions, so behavioural features are
weakly supported. Fraud exists in only 2 of 5 transaction types — a dataset artefact, not a real-world rule. At
its best threshold the system misses about half of all fraud. The tuner gave the rule engine zero weight, and
that is reported rather than hidden.

**The disclaimer.** An academic prototype. No real card data, ever. Public-dataset metrics do not establish
production banking performance.

---

*End of report.*




