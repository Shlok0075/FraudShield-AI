"""
FraudShield AI - Prediction Service (PART 7, Week 6)
======================================================
Loads the trained model + scaler ONCE and exposes a single function:

    predict(feature_dict) -> {
        probability, risk_score, risk_level, decision,
        create_alert, alert_severity, explanation
    }

This is the EXACT function the FastAPI backend imports
(backend/app/ml/model_service.py wraps this module so the model is only
loaded once at process startup).

Explainability: SHAP TreeExplainer for tree-based models (RandomForest /
XGBoost), producing the top-N contributing features with direction, e.g.:
    Fraud Risk: 87%  Risk Level: HIGH
    Main Reasons: Unusual transaction amount, New device, ...
Always presented as a model-derived statistical indicator, not proof of
fraud -- a human must review before any real action is taken.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import joblib
import numpy as np

SRC_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SRC_DIR))
from decision_engine import evaluate  # noqa: E402
from preprocessing import FEATURE_COLUMNS  # noqa: E402

MODELS_DIR = SRC_DIR.parent / "models"

_model = None
_scaler = None
_explainer = None

# Human-readable labels for the raw feature names, used in explanations
FEATURE_LABELS = {
    "Amount_scaled": "Unusual transaction amount",
    "Time_scaled": "Unusual time of transaction",
    **{f"V{i}": f"Anonymized pattern signal V{i}" for i in range(1, 29)},
}


def _load():
    global _model, _scaler, _explainer
    if _model is None:
        _model = joblib.load(MODELS_DIR / "model.joblib")
    if _scaler is None:
        _scaler = joblib.load(MODELS_DIR / "scaler.joblib")
    if _explainer is None:
        try:
            import shap
            _explainer = shap.TreeExplainer(_model)
        except Exception:
            _explainer = None  # falls back to coefficient/importance-based explanation
    return _model, _scaler, _explainer


def _feature_vector(feature_dict: dict) -> np.ndarray:
    """Builds the feature vector in the EXACT order the model was trained
    on (see metadata.json['feature_columns']). Missing V-features default
    to 0.0; Amount/Time must already be pre-scaled by the caller using the
    same fitted scaler (see backend/app/services/feature_engineering.py)."""
    row = []
    for col in FEATURE_COLUMNS:
        row.append(float(feature_dict.get(col, 0.0)))
    return np.array(row, dtype=float).reshape(1, -1)


def explain_prediction(X_row: np.ndarray, top_n: int = 4) -> list[dict]:
    """Returns top-N contributing features with direction (SHAP if
    available, else falls back to model feature_importances_ / coef_)."""
    model, _, explainer = _load()

    if explainer is not None:
        shap_values = explainer.shap_values(X_row)
        values = shap_values[1][0] if isinstance(shap_values, list) else shap_values[0]
    else:
        importances = getattr(model, "feature_importances_", None)
        if importances is None:
            importances = np.abs(getattr(model, "coef_", np.zeros((1, X_row.shape[1])))[0])
        values = importances * X_row[0]

    order = np.argsort(-np.abs(values))[:top_n]
    explanation = []
    for idx in order:
        col = FEATURE_COLUMNS[idx]
        impact = float(values[idx])
        explanation.append({
            "feature": col,
            "label": FEATURE_LABELS.get(col, col),
            "impact": round(impact, 4),
            "direction": "increases_risk" if impact > 0 else "decreases_risk",
        })
    return explanation


def predict(feature_dict: dict, model_version: Optional[str] = None) -> dict:
    """Main entrypoint used by the backend's ML wrapper."""
    model, _, _ = _load()
    X_row = _feature_vector(feature_dict)

    proba = float(model.predict_proba(X_row)[0, 1])
    decision_result = evaluate(proba)
    explanation = explain_prediction(X_row)

    return {
        "probability": round(proba, 4),
        "risk_score": decision_result.risk_score,
        "risk_level": decision_result.risk_level,
        "decision": decision_result.decision,
        "create_alert": decision_result.create_alert,
        "alert_severity": decision_result.alert_severity,
        "explanation": explanation,
        "model_version": model_version or "loaded-from-joblib",
    }


if __name__ == "__main__":
    # Quick manual smoke test with a hand-crafted "clearly fraud-like" row
    example = {"V4": 3.5, "V11": 3.2, "Amount_scaled": 4.0, "Time_scaled": 0.1}
    result = predict(example)
    print("Example prediction:", result)
