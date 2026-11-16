"""Shared behavioral ML + hybrid risk service.

Loads the new live-v1 XGBoost/Isolation Forest artifacts and the tuned
RiskConfig once at application startup. The legacy anonymized model remains
available as a fallback only when the new artifacts are absent.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np

from app.config.settings import settings

_ML_SRC = Path(__file__).resolve().parents[3] / "ml" / "src"
if str(_ML_SRC) not in sys.path:
    sys.path.insert(0, str(_ML_SRC))

from fraudpipe.risk_engine import RiskConfig, score_transaction, _ok  # noqa: E402
from fraudpipe.graph_engine import build_graph_features  # noqa: E402


class ModelService:
    _loaded = False
    _metadata: dict | None = None
    _model = None
    _anomaly = None
    _config: RiskConfig | None = None
    _explainer = None
    _feature_columns: list[str] = []
    _medians: dict[str, float] = {}

    @classmethod
    def _models_root(cls) -> Path:
        configured = Path(settings.ML_MODELS_DIR)
        root = configured if configured.is_absolute() else Path(__file__).resolve().parents[3] / "ml" / "models"
        return root

    @classmethod
    def load(cls):
        if cls._loaded:
            return
        live = cls._models_root() / "live-v1"
        metadata_file = live / "metadata.json"
        if not metadata_file.exists():
            raise RuntimeError("live-v1 model artifacts are missing; run `python ml/src/train_live_model.py`")
        cls._metadata = json.loads(metadata_file.read_text())
        cls._model = joblib.load(live / "supervised.joblib")
        cls._anomaly = joblib.load(live / "isolation_forest.joblib")
        prep = json.loads((live / "preprocessor.json").read_text())
        cls._feature_columns = prep["feature_columns"]
        cls._medians = prep["medians"]
        cls._config = RiskConfig.from_json((live / "risk_config.json").read_text())
        try:
            import shap
            cls._explainer = shap.TreeExplainer(cls._model)
        except Exception:
            cls._explainer = None
        cls._loaded = True

    @classmethod
    def _matrix(cls, feature_dict: dict) -> np.ndarray:
        values = []
        for col in cls._feature_columns:
            value = feature_dict.get(col, cls._medians.get(col, 0.0))
            try:
                value = float(value)
            except (TypeError, ValueError):
                value = cls._medians.get(col, 0.0)
            if not np.isfinite(value):
                value = cls._medians.get(col, 0.0)
            values.append(value)
        return np.asarray(values, dtype=float).reshape(1, -1)

    @classmethod
    def bulk_predict(cls, features_batch: list[dict]) -> list[dict]:
        """Score a large batch without per-row SHAP (used by the PaySim bulk
        ingestion path). Real-time requests still go through ``predict`` which
        attaches a SHAP explanation."""
        cls.load()
        if not features_batch:
            return []
        X = np.vstack([cls._matrix(f) for f in features_batch])
        ml_probs = cls._model.predict_proba(X)[:, 1]
        anomalies = np.array([cls._anomaly_score(X[i:i + 1]) for i in range(len(X))])
        out = []
        for i, f in enumerate(features_batch):
            graph_features = f.get("_graph_features", {})
            graph_score = graph_features.get("graph_risk")

            cfg = cls._config
            cfg.amount = float(f.get("amount", 0.0))
            cfg.user_prior_txn_count = int(f.get("user_txn_count_prior", 0))
            cfg.merchant_fraud_rate = float(f.get("counterparty_fraud_rate_prior", 0.0))
            cfg.hour_of_day = int(f.get("hour_of_day", 12)) if _ok(f.get("hour_of_day")) else None
            cfg.is_weekend = bool(f.get("is_weekend", False))
            cfg.use_adaptive_thresholds = True

            result = score_transaction(
                f, ml_prob=float(ml_probs[i]), anomaly=float(anomalies[i]),
                graph_score=graph_score, cfg=cfg)
            reasons = result.pop("reasons")
            out.append({
                "probability": round(float(ml_probs[i]), 4),
                "risk_score": result["risk_score"],
                "risk_level": result["risk_level"],
                "decision": result["decision"],
                "final_risk_score": result.get("final_risk_score"),
                "anomaly_score": result.get("anomaly_score"),
                "behavior_score": result.get("behavior_score"),
                "rule_score": result.get("rule_score"),
                "graph_score": result.get("graph_score"),
                "triggered_rules": result.get("triggered_rules", []),
                "reasons": reasons,
                "signal_contributions": result.get("signal_contributions", {}),
                "weights_used": result.get("weights_used", {}),
                "model_version": cls._metadata.get("version", "live-hybrid-v1"),
                "explanation": None,  # bulk path: no SHAP, see predict() for live rows
                "create_alert": result["decision"] != "ALLOW",
                "alert_severity": result["risk_level"] if result["decision"] != "ALLOW" else None,
            })
        return out

    @classmethod
    def _anomaly_score(cls, X: np.ndarray) -> float:
        # The training metadata stores the normalization implicitly through
        # the training artifact. Recompute the train distribution from the
        # persisted Isolation Forest's score_samples on its training set is
        # impossible after serialization, so use a stable sigmoid-like map
        # around the model's score range. This is a relative risk signal, not
        # a calibrated probability.
        raw = float(-cls._anomaly.score_samples(X)[0])
        lo = float(cls._metadata.get("anomaly_score_low", 0.0))
        hi = float(cls._metadata.get("anomaly_score_high", 1.0))
        return float(np.clip((raw - lo) / max(hi - lo, 1e-9), 0.0, 1.0))

    @classmethod
    def _explain(cls, X: np.ndarray) -> list[dict]:
        values = None
        if cls._explainer is not None:
            try:
                sv = cls._explainer.shap_values(X)
                if isinstance(sv, list):
                    values = np.asarray(sv[-1])[0]
                else:
                    arr = np.asarray(sv)
                    values = arr[0] if arr.ndim > 1 else arr
            except Exception:
                values = None
        if values is None:
            imp = getattr(cls._model, "feature_importances_", np.ones(len(cls._feature_columns)))
            values = np.asarray(imp) * X[0]
        labels = {
            "amount": "Transaction amount",
            "amount_vs_user_avg": "Amount vs user average",
            "amount_zscore": "Amount z-score",
            "txn_count_1m": "Transactions in last minute",
            "txn_count_5m": "Transactions in last 5 minutes",
            "txn_count_1h": "Transactions in last hour",
            "new_device": "New device",
            "known_device_count": "Known device count",
            "location_change": "Location change",
            "distance_from_prev_km": "Distance from previous location",
            "implied_speed_kmh": "Implied travel speed",
            "unusual_hour": "Unusual transaction hour",
            "user_fraud_rate_prior": "Prior user fraud rate",
            "counterparty_fraud_rate_prior": "Prior counterparty fraud rate",
        }
        order = np.argsort(-np.abs(values))[:6]
        return [{
            "feature": cls._feature_columns[i],
            "label": labels.get(cls._feature_columns[i], cls._feature_columns[i]),
            "impact": round(float(values[i]), 4),
            "direction": "increases_risk" if values[i] > 0 else "decreases_risk",
        } for i in order]

    @classmethod
    def predict(cls, feature_dict: dict) -> dict:
        cls.load()
        X = cls._matrix(feature_dict)
        ml_prob = float(cls._model.predict_proba(X)[0, 1])
        anomaly = cls._anomaly_score(X)

        # Graph-based fraud ring features
        graph_features = feature_dict.get("_graph_features", {})
        graph_score = graph_features.get("graph_risk")

        # Build context for adaptive thresholds
        cfg = cls._config
        cfg.amount = float(feature_dict.get("amount", 0.0))
        cfg.user_prior_txn_count = int(feature_dict.get("user_txn_count_prior", 0))
        cfg.merchant_fraud_rate = float(feature_dict.get("counterparty_fraud_rate_prior", 0.0))
        cfg.hour_of_day = int(feature_dict.get("hour_of_day", 12)) if _ok(feature_dict.get("hour_of_day")) else None
        cfg.is_weekend = bool(feature_dict.get("is_weekend", False))
        cfg.use_adaptive_thresholds = True

        result = score_transaction(feature_dict, ml_prob=ml_prob, anomaly=anomaly,
                                   graph_score=graph_score, cfg=cfg)
        reasons = result.pop("reasons")
        explanation = cls._explain(X)
        explanation.extend({"feature": "rule", "label": r["description"], "impact": r["points"], "direction": "increases_risk"}
                           for r in result["triggered_rules"])
        result.update({
            "probability": round(ml_prob, 4),
            "model_version": cls._metadata.get("version", "live-hybrid-v1"),
            "explanation": explanation,
            "reasons": reasons,
            "create_alert": result["decision"] != "ALLOW",
            "alert_severity": result["risk_level"] if result["decision"] != "ALLOW" else None,
        })
        return result

    @classmethod
    def metadata(cls) -> dict:
        cls.load()
        return cls._metadata or {}
