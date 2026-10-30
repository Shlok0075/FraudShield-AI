"""
FraudShield AI - Synthetic Dataset Generator
=============================================
Generates a dataset that mirrors the structure of the well-known
"Credit Card Fraud Detection" (ULB) Kaggle dataset:
  Time, V1..V28 (PCA-like anonymized features), Amount, Class

WHY SYNTHETIC: the original Kaggle dataset requires a Kaggle account /
API token to download and cannot be redistributed here. This generator
produces a dataset with the SAME schema, class-imbalance ratio (~0.17%
fraud) and statistical shape (fraud rows shifted in a subset of the V
features + higher/lower amount patterns) so the full ML pipeline in this
handbook (EDA -> preprocessing -> imbalance handling -> training ->
evaluation -> explainability) can be exercised end-to-end.

Academic disclaimer: this is SYNTHETIC data for a student prototype.
It is not real transaction data and must never be treated as such.
If you have access to the real ULB dataset (creditcard.csv), drop it
into ml/data/raw/creditcard.csv and this generator is not needed --
the rest of the pipeline (preprocessing.py, train.py) works unchanged
on either file, since the schema is identical.
"""
import numpy as np
import pandas as pd
from pathlib import Path

RANDOM_STATE = 42
N_SAMPLES = 120_000       # kept smaller than the real 284,807 rows so the
                          # full pipeline trains in seconds on a student laptop,
                          # while still giving a large enough fraud count in
                          # the test split for stable metrics
FRAUD_RATIO = 0.0017      # ~0.17%, matches the real dataset's imbalance
N_V_FEATURES = 28

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def generate(n_samples: int = N_SAMPLES, fraud_ratio: float = FRAUD_RATIO,
             random_state: int = RANDOM_STATE) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)

    n_fraud = max(1, int(n_samples * fraud_ratio))
    n_legit = n_samples - n_fraud

    # --- Time: seconds elapsed since first transaction (2 days of activity) ---
    time_legit = rng.uniform(0, 172800, n_legit)
    time_fraud = rng.uniform(0, 172800, n_fraud)

    # --- V1..V28: PCA-like anonymized features ---
    # Legitimate: standard normal (mirrors PCA-whitened components).
    v_legit = rng.normal(loc=0.0, scale=1.0, size=(n_legit, N_V_FEATURES))
    # Fraud: shifted on a subset of components to create a learnable but
    # DELIBERATELY OVERLAPPING signal -- real fraud detection is never
    # perfectly separable, and a dataset that yields 100% accuracy would
    # be pedagogically wrong (it would hide the whole point of PR-AUC /
    # precision-recall tradeoffs this handbook is built around). Only a
    # majority of fraud rows get a moderate shift; a minority ("hard
    # fraud") is left statistically close to legitimate traffic so the
    # trained model realistically misses some of it (false negatives) and
    # occasionally misflags a legitimate row (false positives).
    v_fraud = rng.normal(loc=0.0, scale=1.0, size=(n_fraud, N_V_FEATURES))
    signal_components = [1, 3, 4, 10, 11, 13, 16, 17]  # arbitrary subset
    is_hard_fraud = rng.random(n_fraud) < 0.35  # ~35% of fraud is "hard" (subtle)
    for idx in signal_components:
        shift = rng.choice([-1, 1]) * rng.uniform(1.0, 1.8)
        v_fraud[~is_hard_fraud, idx] += shift
        v_fraud[is_hard_fraud, idx] += shift * 0.25  # much weaker signal

    # --- Amount: legit follows a log-normal skew; fraud skews higher on
    # average but with more variance (mirrors real-world fraud patterns
    # of unusually large or oddly precise amounts) ---
    amount_legit = np.round(rng.lognormal(mean=3.0, sigma=1.2, size=n_legit), 2)
    amount_fraud = np.round(rng.lognormal(mean=3.6, sigma=1.5, size=n_fraud), 2)
    amount_legit = np.clip(amount_legit, 0.5, 25000)
    amount_fraud = np.clip(amount_fraud, 0.5, 25000)

    df_legit = pd.DataFrame(v_legit, columns=[f"V{i+1}" for i in range(N_V_FEATURES)])
    df_legit["Time"] = time_legit
    df_legit["Amount"] = amount_legit
    df_legit["Class"] = 0

    df_fraud = pd.DataFrame(v_fraud, columns=[f"V{i+1}" for i in range(N_V_FEATURES)])
    df_fraud["Time"] = time_fraud
    df_fraud["Amount"] = amount_fraud
    df_fraud["Class"] = 1

    df = pd.concat([df_legit, df_fraud], ignore_index=True)
    df = df.sample(frac=1, random_state=random_state).reset_index(drop=True)

    col_order = ["Time"] + [f"V{i+1}" for i in range(N_V_FEATURES)] + ["Amount", "Class"]
    return df[col_order]


if __name__ == "__main__":
    df = generate()
    out_path = RAW_DIR / "creditcard.csv"
    df.to_csv(out_path, index=False)
    print(f"Wrote {len(df):,} rows ({df['Class'].sum()} fraud, "
          f"{df['Class'].mean()*100:.4f}% fraud rate) -> {out_path}")
