"""
FraudShield AI - Model Training & Comparison (PART 6 Week 4, PART 7 Week 5)
=============================================================================
Trains 3 algorithms (Logistic Regression, Random Forest, XGBoost) under
2 imbalance strategies (class_weight='balanced' and SMOTE), evaluates all
6 variants on Precision/Recall/F1/ROC-AUC/PR-AUC + confusion matrix, and
saves:
  - ml/models/model.joblib          (best performing pipeline)
  - ml/models/scaler.joblib         (already saved by preprocessing.py)
  - ml/models/metadata.json         (version, training date, metrics, features)
  - ml/models/model_comparison.csv  (the 6-variant comparison table, PART 10.10)

Run:  python ml/src/train.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_val_score
from xgboost import XGBClassifier

SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR))
from preprocessing import run_preprocessing_pipeline, apply_smote, FEATURE_COLUMNS  # noqa: E402

ML_ROOT = SRC_DIR.parent
MODELS_DIR = ML_ROOT / "models"
RAW_CSV = ML_ROOT / "data" / "raw" / "creditcard.csv"
RANDOM_STATE = 42


def metrics_for(y_true, y_pred, y_proba) -> dict:
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    return {
        "precision": round(float(precision_score(y_true, y_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_true, y_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, y_pred, zero_division=0)), 4),
        "roc_auc": round(float(roc_auc_score(y_true, y_proba)), 4),
        "pr_auc": round(float(average_precision_score(y_true, y_proba)), 4),
        "tp": int(tp), "fp": int(fp), "tn": int(tn), "fn": int(fn),
    }


def build_models(scale_pos_weight: float) -> dict:
    return {
        "LogisticRegression": LogisticRegression(
            class_weight="balanced", max_iter=1000, random_state=RANDOM_STATE
        ),
        "RandomForest": RandomForestClassifier(
            n_estimators=200, max_depth=12, min_samples_leaf=2,
            class_weight="balanced", random_state=RANDOM_STATE, n_jobs=-1
        ),
        "XGBoost": XGBClassifier(
            n_estimators=200, max_depth=6, learning_rate=0.1,
            scale_pos_weight=scale_pos_weight, eval_metric="aucpr",
            random_state=RANDOM_STATE, use_label_encoder=False, n_jobs=-1
        ),
    }


def main():
    print("== FraudShield AI :: Model Training & Comparison ==")
    if not RAW_CSV.exists():
        print(f"Raw dataset not found at {RAW_CSV}. Generating synthetic dataset...")
        from generate_dataset import generate
        RAW_CSV.parent.mkdir(parents=True, exist_ok=True)
        generate().to_csv(RAW_CSV, index=False)

    data = run_preprocessing_pipeline(RAW_CSV)
    X_train, X_test = data["X_train"], data["X_test"]
    y_train, y_test = data["y_train"], data["y_test"]

    scale_pos_weight = (y_train == 0).sum() / max(1, (y_train == 1).sum())

    results = []
    trained_models = {}

    # ---- Strategy A: class_weight='balanced' (train directly) ----
    for name, model in build_models(scale_pos_weight).items():
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)[:, 1]
        pred = (proba >= 0.5).astype(int)
        m = metrics_for(y_test, pred, proba)
        m.update({"model": name, "imbalance_strategy": "class_weight"})
        results.append(m)
        trained_models[f"{name}_class_weight"] = model
        print(f"[class_weight] {name:<20} PR-AUC={m['pr_auc']:.4f} "
              f"ROC-AUC={m['roc_auc']:.4f} F1={m['f1']:.4f}")

    # ---- Strategy B: SMOTE (fit on train fold only, never on test) ----
    X_train_sm, y_train_sm = apply_smote(X_train, y_train, RANDOM_STATE)
    for name, model in build_models(scale_pos_weight=1.0).items():
        model.fit(X_train_sm, y_train_sm)
        proba = model.predict_proba(X_test)[:, 1]
        pred = (proba >= 0.5).astype(int)
        m = metrics_for(y_test, pred, proba)
        m.update({"model": name, "imbalance_strategy": "SMOTE"})
        results.append(m)
        trained_models[f"{name}_SMOTE"] = model
        print(f"[SMOTE]        {name:<20} PR-AUC={m['pr_auc']:.4f} "
              f"ROC-AUC={m['roc_auc']:.4f} F1={m['f1']:.4f}")

    comparison_df = pd.DataFrame(results)[
        ["model", "imbalance_strategy", "precision", "recall", "f1",
         "roc_auc", "pr_auc", "tp", "fp", "tn", "fn"]
    ]
    comparison_df.to_csv(MODELS_DIR / "model_comparison.csv", index=False)
    print("\nComparison table saved -> ml/models/model_comparison.csv")
    print(comparison_df.to_string(index=False))

    # ---- Select best model by PR-AUC (most informative under heavy imbalance) ----
    best_row = comparison_df.loc[comparison_df["pr_auc"].idxmax()]
    best_key = f"{best_row['model']}_{best_row['imbalance_strategy']}"
    best_model = trained_models[best_key]

    # ---- Quick 5-fold CV sanity check on the winning model's training data ----
    if best_row["imbalance_strategy"] == "SMOTE":
        cv_X, cv_y = X_train_sm, y_train_sm
    else:
        cv_X, cv_y = X_train, y_train
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_STATE)
    cv_scores = cross_val_score(best_model, cv_X, cv_y, cv=skf, scoring="average_precision")

    print(f"\nBEST MODEL: {best_key}  "
          f"(PR-AUC={best_row['pr_auc']:.4f}, 5-fold CV PR-AUC mean={cv_scores.mean():.4f})")

    joblib.dump(best_model, MODELS_DIR / "model.joblib")

    metadata = {
        "version": f"{best_row['model'].lower()}-v1",
        "algorithm": best_row["model"],
        "imbalance_strategy": best_row["imbalance_strategy"],
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "feature_columns": FEATURE_COLUMNS,
        "metrics": {
            "precision": best_row["precision"],
            "recall": best_row["recall"],
            "f1": best_row["f1"],
            "roc_auc": best_row["roc_auc"],
            "pr_auc": best_row["pr_auc"],
            "cv_pr_auc_mean": round(float(cv_scores.mean()), 4),
        },
        "risk_thresholds": {"LOW": [0, 29], "MEDIUM": [30, 59], "HIGH": [60, 79], "CRITICAL": [80, 100]},
        "dataset": "synthetic (creditcard-schema, ~0.17% fraud) -- see docs/dataset_choice.md",
        "n_train": int(len(y_train)),
        "n_test": int(len(y_test)),
        "disclaimer": "Academic prototype model. Trained on public/synthetic data only.",
    }
    with open(MODELS_DIR / "metadata.json", "w") as f:
        json.dump(metadata, f, indent=2)
    print("Saved model.joblib + metadata.json -> ml/models/")


if __name__ == "__main__":
    main()
