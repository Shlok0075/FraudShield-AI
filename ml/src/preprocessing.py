"""
FraudShield AI - Preprocessing module (PART 6, Week 3)
=======================================================
Reusable, leakage-free preprocessing functions:
  - stratified train/validation/test split
  - StandardScaler fit on TRAIN ONLY (Time, Amount), applied to val/test
  - class-imbalance handling: class_weight (built-in) or SMOTE (train-only)
  - data validation: missing values, duplicates, feature types

Data-leakage rule enforced throughout this module: any fitted transformer
(scaler, encoder, SMOTE) is fit ONLY on the training split and then
applied (never re-fit) to the validation/test splits. See docs/data_leakage_notes.md
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
    """Load the raw creditcard-schema CSV (real or synthetic).

    Validates required columns, checks for missing values and duplicates,
    and removes exact duplicate rows (kept only from training side later).
    """
    df = pd.read_csv(path)
    required = {"Time", "Amount", "Class"} | {f"V{i}" for i in range(1, 29)}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Dataset missing required columns: {missing}")

    # Report data quality
    n_missing = int(df.isna().sum().sum())
    n_dupes = int(df.duplicated().sum())
    print(f"[preprocess] loaded {len(df)} rows, missing_values={n_missing}, duplicate_rows={n_dupes}")

    if n_missing > 0:
        # Impute numeric columns with median, categorical with mode
        for col in df.columns:
            if df[col].isna().any():
                if pd.api.types.is_numeric_dtype(df[col]):
                    df[col] = df[col].fillna(df[col].median())
                else:
                    df[col] = df[col].fillna(df[col].mode()[0] if not df[col].mode().empty else 0)
        print(f"[preprocess] imputed missing values")

    if n_dupes > 0:
        df = df.drop_duplicates().reset_index(drop=True)
        print(f"[preprocess] removed {n_dupes} duplicate rows")

    return df


def stratified_split(
    df: pd.DataFrame, test_size: float = 0.2, val_size: float = 0.0, random_state: int = 42
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame | None]:
    """Split BEFORE any fitting happens, stratified on Class so both
    splits keep the same fraud percentage.

    Returns (train_df, test_df, val_df_or_None).
    If val_size > 0, carves a validation set out of the training portion.
    """
    # First split: train_val vs test
    train_val_df, test_df = train_test_split(
        df, test_size=test_size, stratify=df[TARGET_COLUMN], random_state=random_state
    )

    val_df = None
    if val_size > 0:
        # Adjust val_size relative to train_val portion
        val_relative = val_size / (1.0 - test_size)
        train_df, val_df = train_test_split(
            train_val_df, test_size=val_relative,
            stratify=train_val_df[TARGET_COLUMN], random_state=random_state
        )
        train_val_df = train_df

    return train_val_df.reset_index(drop=True), test_df.reset_index(drop=True), (
        val_df.reset_index(drop=True) if val_df is not None else None
    )


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
    raw_csv_path: str | Path, save_artifacts: bool = True,
    test_size: float = 0.2, val_size: float = 0.1,
) -> dict:
    """End-to-end: load -> validate -> split (train/val/test) -> scale -> feature matrices.

    Returns a dict with X_train, X_val, X_test, y_train, y_val, y_test and
    the fitted scaler, and optionally persists the scaler + processed CSVs.

    Data-leakage rule: scaler is fit on TRAIN only, then applied to val/test.
    SMOTE (if applied later) must be on TRAIN only.
    """
    df = load_raw_dataset(raw_csv_path)
    train_df, test_df, val_df = stratified_split(
        df, test_size=test_size, val_size=val_size, random_state=42)

    scaler = fit_scaler(train_df)
    train_scaled = apply_scaler(train_df, scaler)
    test_scaled = apply_scaler(test_df, scaler)
    val_scaled = apply_scaler(val_df, scaler) if val_df is not None else None

    X_train, y_train = build_feature_matrix(train_scaled)
    X_test, y_test = build_feature_matrix(test_scaled)
    X_val, y_val = build_feature_matrix(val_scaled) if val_scaled is not None else (None, None)

    if save_artifacts:
        joblib.dump(scaler, MODELS_DIR / "scaler.joblib")
        processed_dir = Path(raw_csv_path).resolve().parents[1] / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)
        train_scaled.to_csv(processed_dir / "train.csv", index=False)
        test_scaled.to_csv(processed_dir / "test.csv", index=False)
        if val_scaled is not None:
            val_scaled.to_csv(processed_dir / "val.csv", index=False)

    return {
        "X_train": X_train,
        "X_val": X_val,
        "X_test": X_test,
        "y_train": y_train,
        "y_val": y_val,
        "y_test": y_test,
        "scaler": scaler,
        "feature_columns": FEATURE_COLUMNS,
    }


if __name__ == "__main__":
    raw_path = Path(__file__).resolve().parents[1] / "data" / "raw" / "creditcard.csv"
    result = run_preprocessing_pipeline(raw_path)
    print("Train shape:", result["X_train"].shape, "Fraud in train:", result["y_train"].sum())
    if result["X_val"] is not None:
        print("Val shape:", result["X_val"].shape, "Fraud in val:", result["y_val"].sum())
    print("Test shape:", result["X_test"].shape, "Fraud in test:", result["y_test"].sum())
