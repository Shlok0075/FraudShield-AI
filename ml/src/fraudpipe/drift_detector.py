"""
FraudShield AI — Concept drift detection for online learning.

Monitors model performance and feature distributions over time. When significant
drift is detected, the system can trigger incremental retraining. Results are
persisted to the DriftSnapshot table via the backend API.

Implements an ADWIN-like sliding-window detector on the model's fraud probability
output, plus a PSI (Population Stability Index) check on key feature distributions.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class DriftConfig:
    window_size: int = 500          # sliding window of recent predictions
    min_samples: int = 100          # need this many before drift detection activates
    psi_threshold: float = 0.25     # PSI > 0.25 indicates significant feature shift
    prob_drift_threshold: float = 0.15  # mean prob shift > 15% triggers alert


@dataclass
class DriftSnapshotResult:
    metric: str
    value: float
    status: str  # "stable", "warning", "drift"
    details: dict[str, Any] | None = None


class DriftDetector:
    """Sliding-window concept drift detector.

    Tracks:
      1. Mean predicted fraud probability over a sliding window
      2. PSI of key features between reference and current window
    """

    def __init__(self, config: DriftConfig | None = None):
        self.cfg = config or DriftConfig()
        self._prob_window: deque[float] = deque(maxlen=self.cfg.window_size)
        self._reference_probs: list[float] = []  # baseline from validation/training
        self._reference_feature_stats: dict[str, tuple[float, float]] = {}  # (mean, std)
        self._current_feature_stats: dict[str, tuple[float, float]] = {}
        self._window_count = 0

    def set_reference(self, probs: list[float], feature_stats: dict[str, tuple[float, float]]) -> None:
        """Set the reference (baseline) distribution from training/validation data."""
        self._reference_probs = list(probs)
        self._reference_feature_stats = dict(feature_stats)
        self._current_feature_stats = {}
        self._prob_window.clear()
        self._window_count = 0

    def observe(self, prob: float, features: dict[str, float] | None = None) -> DriftSnapshotResult:
        """Observe a new prediction and check for drift."""
        self._prob_window.append(prob)
        self._window_count += 1

        if self._window_count < self.cfg.min_samples:
            return DriftSnapshotResult(
                metric="probability_drift", value=0.0, status="stable",
                details={"samples": self._window_count, "note": "insufficient samples"})

        # Check probability drift
        recent_mean = sum(self._prob_window) / len(self._prob_window)
        if self._reference_probs:
            ref_mean = sum(self._reference_probs) / len(self._reference_probs)
            prob_shift = abs(recent_mean - ref_mean)
        else:
            prob_shift = 0.0

        prob_status = "stable"
        if prob_shift > self.cfg.prob_drift_threshold:
            prob_status = "drift"
        elif prob_shift > self.cfg.prob_drift_threshold * 0.5:
            prob_status = "warning"

        # Check feature PSI drift
        psi_results: dict[str, float] = {}
        max_psi = 0.0
        if features is not None and self._reference_feature_stats:
            for fname, fval in features.items():
                if fname in self._reference_feature_stats:
                    ref_mean, ref_std = self._reference_feature_stats[fname]
                    # Approximate PSI using a single point: z-score deviation
                    if ref_std > 0:
                        z = abs((fval - ref_mean) / ref_std)
                        psi = min(1.0, z / 3.0)  # normalise to [0,1]
                    else:
                        psi = 0.0
                    psi_results[fname] = round(psi, 4)
                    max_psi = max(max_psi, psi)

        # Update running stats for future reference
        if features is not None:
            for fname, fval in features.items():
                if fname not in self._current_feature_stats:
                    self._current_feature_stats[fname] = (fval, 0.0)
                else:
                    cur_mean, cur_std = self._current_feature_stats[fname]
                    n = self._window_count
                    new_mean = cur_mean + (fval - cur_mean) / n
                    new_std = math.sqrt(cur_std**2 + (fval - cur_mean) * (fval - new_mean)) if n > 1 else 0.0
                    self._current_feature_stats[fname] = (new_mean, new_std)

        overall_status = "stable"
        if prob_status == "drift" or max_psi > self.cfg.psi_threshold:
            overall_status = "drift"
        elif prob_status == "warning" or max_psi > self.cfg.psi_threshold * 0.5:
            overall_status = "warning"

        return DriftSnapshotResult(
            metric="probability_drift",
            value=round(prob_shift, 4),
            status=overall_status,
            details={
                "recent_mean_prob": round(recent_mean, 4),
                "ref_mean_prob": round(sum(self._reference_probs) / len(self._reference_probs), 4) if self._reference_probs else 0.0,
                "psi_features": psi_results,
                "max_psi": round(max_psi, 4),
                "samples": self._window_count,
            },
        )


_detector: DriftDetector | None = None


def get_drift_detector() -> DriftDetector:
    global _detector
    if _detector is None:
        _detector = DriftDetector()
    return _detector
