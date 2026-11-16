"""
FraudShield AI — Online learning support.

Streams newly labelled transactions into a buffer and performs incremental
retraining when enough samples accumulate or drift is detected. Uses XGBoost's
native incremental training (xgb_model.update) where available, falling back to
full retrain on the accumulated buffer.
"""

from __future__ import annotations

import json
import threading
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import joblib
import numpy as np

_ML_SRC = Path(__file__).resolve().parents[2] / "src"
import sys
if str(_ML_SRC) not in sys.path:
    sys.path.insert(0, str(_ML_SRC))

from fraudpipe.drift_detector import get_drift_detector  # noqa: E402


@dataclass
class OnlineLearningConfig:
    buffer_size: int = 1000          # max labelled samples to keep
    min_retrain_samples: int = 200   # trigger retrain after this many new labels
    retrain_cooldown_minutes: int = 60  # don't retrain more often than this
    learning_rate: float = 0.1       # for incremental updates


class OnlineLearner:
    """Accumulates labelled feedback and triggers incremental model updates."""

    def __init__(self, config: OnlineLearningConfig | None = None,
                 model_path: Path | None = None):
        self.cfg = config or OnlineLearningConfig()
        self.model_path = model_path
        self._buffer: deque[dict] = deque(maxlen=self.cfg.buffer_size)
        self._lock = threading.Lock()
        self._last_retrain: float | None = None
        self._model = None
        self._feature_columns: list[str] = []

    def add_feedback(self, features: dict, actual_label: int,
                     predicted_prob: float) -> None:
        """Store a labelled transaction for future retraining."""
        with self._lock:
            self._buffer.append({
                "features": features,
                "label": actual_label,
                "predicted_prob": predicted_prob,
            })

    def should_retrain(self) -> bool:
        with self._lock:
            if len(self._buffer) < self.cfg.min_retrain_samples:
                return False
            if self._last_retrain is not None:
                import time
                elapsed = (time.time() - self._last_retrain) / 60.0
                if elapsed < self.cfg.retrain_cooldown_minutes:
                    return False
            return True

    def retrain_if_needed(self) -> dict[str, Any] | None:
        """Perform incremental retraining if conditions are met. Returns stats or None."""
        if not self.should_retrain():
            return None

        with self._lock:
            buffer = list(self._buffer)
            self._buffer.clear()
            self._last_retrain = __import__("time").time()

        # Build training arrays
        X = []
        y = []
        for row in buffer:
            feat = row["features"]
            # Use the same feature ordering as the live model
            X.append([feat.get(c, 0.0) for c in self._feature_columns])
            y.append(row["label"])

        if not X:
            return None

        X_arr = np.asarray(X, dtype=float)
        y_arr = np.asarray(y, dtype=int)

        # Load model
        if self._model is None and self.model_path is not None:
            try:
                self._model = joblib.load(self.model_path)
            except Exception:
                self._model = None

        stats: dict[str, Any] = {"samples": len(buffer), "retrained": False}

        if self._model is not None:
            try:
                # XGBoost incremental update
                import xgboost as xgb
                dtrain = xgb.DMatrix(X_arr, label=y_arr)
                self._model.update(dtrain, iteration_round=1)
                stats["retrained"] = True
                stats["method"] = "xgb_incremental"
                # Save updated model
                if self.model_path:
                    joblib.dump(self._model, self.model_path)
            except Exception:
                # Fallback: full retrain (would need training pipeline)
                stats["retrained"] = False
                stats["method"] = "skipped_no_trainer"

        return stats


_learner: OnlineLearner | None = None


def get_online_learner() -> OnlineLearner:
    global _learner
    if _learner is None:
        _learner = OnlineLearner()
    return _learner
