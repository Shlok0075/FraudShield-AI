"""
FraudShield AI - Preprocessing module (PART 6, Week 3)
=======================================================
Reusable, leakage-free preprocessing functions:
  - stratified train/test split
  - StandardScaler fit on TRAIN ONLY (Time, Amount), applied to test
  - class-imbalance handling: class_weight (built-in) or SMOTE (train-only)

Data-leakage rule enforced throughout this module: any fitted transformer
(scaler, encoder, SMOTE) is fit ONLY on the training split and then
applied (never re-fit) to the test split. See docs/data_leakage_notes.md
for the full explanation with a FraudShield-specific example.
"""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

FEATURE_COLUMNS = [f"V{i}" for i in range(1, 29)] + ["Amount_scaled", "Time_scaled"]
TARGET_COLUMN = "Class"

MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


def load_raw_dataset(path: str | Path) -> pd.DataFrame:
    """Load the raw creditcard-schema CSV (real or synthetic)."""
    df = pd.read_csv(path)
    required = {"Time", "Amount", "Class"} | {f"V{i}" for i in range(1, 29)}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Dataset missing required columns: {missing}")
    return df


def stratified_split(
    df: pd.DataFrame, test_size: float = 0.2, random_state: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Split BEFORE any fitting happens, stratified on Class so both
    splits keep the same fraud percentage."""
    train_df, test_df = train_test_split(
        df, test_size=test_size, stratify=df[TARGET_COLUMN], random_state=random_state
    )
    return train_df.reset_index(drop=True), test_df.reset_index(drop=True)


def fit_scaler(train_df: pd.DataFrame) -> StandardScaler:
    """Fit a StandardScaler on Amount & Time using TRAIN data only."""
    scaler = StandardScaler()
    scaler.fit(train_df[["Amount", "Time"]])
    return scaler


def apply_scaler(df: pd.DataFrame, scaler: StandardScaler) -> pd.DataFrame:
    """Apply an already-fitted scaler (never re-fit) to any split."""
    out = df.copy()
    scaled = scaler.transform(out[["Amount", "Time"]])
    out["Amount_scaled"] = scaled[:, 0]
    out["Time_scaled"] = scaled[:, 1]
    return out


def build_feature_matrix(df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
    X = df[FEATURE_COLUMNS].to_numpy()
    y = df[TARGET_COLUMN].to_numpy()
    return X, y


def apply_smote(X: np.ndarray, y: np.ndarray, random_state: int = 42):
    """Oversample the minority (fraud) class. MUST be applied to the
    TRAINING split only -- never to validation/test data, and never
    before the train/test split."""
    from imblearn.over_sampling import SMOTE

    sm = SMOTE(random_state=random_state)
    X_res, y_res = sm.fit_resample(X, y)
    return X_res, y_res


def run_preprocessing_pipeline(
    raw_csv_path: str | Path, save_artifacts: bool = True
) -> dict:
    """End-to-end: load -> split -> scale -> feature matrices.
    Returns a dict with X_train, X_test, y_train, y_test and the fitted
    scaler, and optionally persists the scaler + processed CSVs."""
    df = load_raw_dataset(raw_csv_path)
    train_df, test_df = stratified_split(df)

    scaler = fit_scaler(train_df)
    train_scaled = apply_scaler(train_df, scaler)
    test_scaled = apply_scaler(test_df, scaler)

    X_train, y_train = build_feature_matrix(train_scaled)
    X_test, y_test = build_feature_matrix(test_scaled)

    if save_artifacts:
        joblib.dump(scaler, MODELS_DIR / "scaler.joblib")
        train_scaled.to_csv(
            Path(raw_csv_path).resolve().parents[1] / "processed" / "train.csv",
            index=False,
        )
        test_scaled.to_csv(
            Path(raw_csv_path).resolve().parents[1] / "processed" / "test.csv",
            index=False,
        )

    return {
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
        "scaler": scaler,
        "feature_columns": FEATURE_COLUMNS,
    }


if __name__ == "__main__":
    raw_path = Path(__file__).resolve().parents[1] / "data" / "raw" / "creditcard.csv"
    result = run_preprocessing_pipeline(raw_path)
    print("Train shape:", result["X_train"].shape, "Fraud in train:", result["y_train"].sum())
    print("Test shape:", result["X_test"].shape, "Fraud in test:", result["y_test"].sum())
