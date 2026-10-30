"""Threshold sweep, cost-sensitive evaluation and operating-mode threshold selection.

Rule: thresholds are CHOSEN on validation scores only; the test set is then evaluated once at those thresholds.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score

THRESHOLDS = [round(float(t), 2) for t in np.arange(0.05, 0.951, 0.05)]
MODES = ("high_recall", "balanced", "high_precision", "min_cost")


@dataclass(frozen=True)
class CostMatrix:
    """Business cost per error. The defaults are ASSUMPTIONS for demonstration, not measured bank costs."""
    fp_cost: float = 5.0      # analyst review time / customer friction for a wrongly flagged txn
    fn_cost: float = 500.0    # average loss from a missed fraud


def confusion(y, pred) -> tuple[int, int, int, int]:
    y = np.asarray(y).astype(bool)
    pred = np.asarray(pred).astype(bool)
    return int((y & pred).sum()), int((~y & pred).sum()), int((~y & ~pred).sum()), int((y & ~pred).sum())


def _safe_div(a, b):
    return float(a / b) if b else 0.0


def metrics_at(y, p, threshold: float, cost: CostMatrix = CostMatrix()) -> dict:
    tp, fp, tn, fn = confusion(y, np.asarray(p) >= threshold)
    prec, rec = _safe_div(tp, tp + fp), _safe_div(tp, tp + fn)
    return {"threshold": threshold, "tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": prec, "recall": rec,
            "f1": _safe_div(2 * prec * rec, prec + rec),
            "fpr": _safe_div(fp, fp + tn), "fnr": _safe_div(fn, fn + tp),
            "cost": fp * cost.fp_cost + fn * cost.fn_cost}


def sweep(y, p, cost: CostMatrix = CostMatrix(), thresholds=THRESHOLDS) -> list[dict]:
    return [metrics_at(y, p, t, cost) for t in thresholds]


def threshold_free(y, p) -> dict:
    y = np.asarray(y)
    p = np.asarray(p, dtype="float64")
    two = len(np.unique(y)) == 2
    return {"pr_auc": float(average_precision_score(y, p)) if two else float("nan"),
            "roc_auc": float(roc_auc_score(y, p)) if two else float("nan"),
            "brier": float(brier_score_loss(y, np.clip(p, 0, 1))),
            "base_rate": float(y.mean())}


def select_thresholds(rows: list[dict], recall_target: float = 0.90, precision_target: float = 0.90) -> dict:
    """Pick one threshold per operating mode from a VALIDATION sweep.

    high_recall    : highest-precision threshold whose recall >= recall_target (else max-recall threshold)
    high_precision : highest-recall threshold whose precision >= precision_target (else max-precision threshold
                     among thresholds that flag at least one transaction)
    balanced       : max F1
    min_cost       : min expected cost under the cost matrix
    Ties resolve to the LOWER-cost / higher threshold deterministically.
    """
    def best(cands, key):
        return max(cands, key=lambda r: (key(r), r["threshold"]))["threshold"]

    hr = [r for r in rows if r["recall"] >= recall_target]
    hp = [r for r in rows if r["precision"] >= precision_target and (r["tp"] + r["fp"]) > 0]
    flagged = [r for r in rows if (r["tp"] + r["fp"]) > 0] or rows
    return {
        "high_recall": best(hr, lambda r: r["precision"]) if hr else best(rows, lambda r: r["recall"]),
        "high_precision": best(hp, lambda r: r["recall"]) if hp else best(flagged, lambda r: r["precision"]),
        "balanced": best(rows, lambda r: r["f1"]),
        "min_cost": max(rows, key=lambda r: (-r["cost"], r["threshold"]))["threshold"],
    }
