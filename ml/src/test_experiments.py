"""Tests for metrics / threshold logic / experiment runner. Run: cd ml/src && pytest test_experiments.py -v"""
import json

import numpy as np
import pytest

from fraudpipe.build_dataset import build
from fraudpipe.experiments import cap_negatives, run
from fraudpipe.gen_paysim_like import make_paysim_like
from fraudpipe.metrics import THRESHOLDS, CostMatrix, confusion, metrics_at, select_thresholds, sweep, threshold_free


def test_threshold_grid():
    assert THRESHOLDS[0] == 0.05 and THRESHOLDS[-1] == 0.95 and len(THRESHOLDS) == 19


def test_confusion_and_metrics_hand_computed():
    y = np.array([1, 1, 1, 0, 0, 0, 0, 0])
    p = np.array([.9, .8, .2, .7, .1, .1, .1, .1])
    assert confusion(y, p >= .5) == (2, 1, 4, 1)
    m = metrics_at(y, p, .5, CostMatrix(fp_cost=2, fn_cost=10))
    assert m["precision"] == pytest.approx(2 / 3) and m["recall"] == pytest.approx(2 / 3)
    assert m["fpr"] == pytest.approx(1 / 5) and m["fnr"] == pytest.approx(1 / 3)
    assert m["cost"] == 1 * 2 + 1 * 10


def test_no_positive_predictions_is_safe():
    m = metrics_at(np.array([1, 0]), np.array([.1, .1]), .5)
    assert m["precision"] == 0.0 and m["recall"] == 0.0 and m["f1"] == 0.0


def test_threshold_free_perfect_and_single_class():
    y = np.array([0, 0, 1, 1])
    assert threshold_free(y, np.array([.1, .2, .8, .9]))["pr_auc"] == pytest.approx(1.0)
    assert np.isnan(threshold_free(np.zeros(4), np.random.rand(4))["roc_auc"])


def test_select_thresholds_modes_and_cost_sensitivity():
    rng = np.random.default_rng(0)
    y = (rng.random(4000) < .05).astype(int)
    p = np.clip(y * .5 + rng.random(4000) * .5, 0, 1)
    rows = sweep(y, p)
    t = select_thresholds(rows)
    by = {r["threshold"]: r for r in rows}
    assert by[t["high_recall"]]["recall"] >= .9 or by[t["high_recall"]]["recall"] == max(r["recall"] for r in rows)
    assert by[t["high_recall"]]["recall"] >= by[t["high_precision"]]["recall"]
    assert by[t["balanced"]]["f1"] == max(r["f1"] for r in rows)
    cheap_fn = select_thresholds(sweep(y, p, CostMatrix(fp_cost=10, fn_cost=1)))["min_cost"]
    dear_fn = select_thresholds(sweep(y, p, CostMatrix(fp_cost=1, fn_cost=1000)))["min_cost"]
    assert dear_fn <= cheap_fn          # costlier misses -> lower (more sensitive) threshold


def test_cap_negatives_keeps_all_fraud_and_is_seeded():
    import pandas as pd
    X = pd.DataFrame({"a": range(1000)})
    y = np.zeros(1000, int)
    y[:20] = 1
    X1, y1 = cap_negatives(X, y, 200, 7)
    X2, y2 = cap_negatives(X, y, 200, 7)
    assert y1.sum() == 20 and len(y1) == 200 and X1.equals(X2)


def test_experiment_runner_smoke_and_test_set_uses_val_thresholds(tmp_path):
    src = tmp_path / "ps.csv"
    make_paysim_like(6000, seed=5).to_csv(src, index=False)
    build(src, tmp_path / "data", seed=42)
    out = run(tmp_path / "data", tmp_path / "exp", seed=42, fast=True, rf_cap=3000, smote_cap=3000)
    assert set(out["results"]) >= {"A_logreg", "C_xgboost", "D_xgboost_class_weight", "E_xgboost_smote",
                                   "F_isolation_forest"}
    for r in out["results"].values():
        for m, d in r["modes"].items():
            assert d["test"]["threshold"] == d["val"]["threshold"] == r["thresholds"][m]
        assert 0 <= r["test"]["pr_auc"] <= 1
    assert (tmp_path / "exp" / "model_comparison.csv").exists()
    assert json.loads((tmp_path / "exp" / "experiment_results.json").read_text())["seed"] == 42
    # determinism
    out2 = run(tmp_path / "data", tmp_path / "exp2", seed=42, fast=True, rf_cap=3000, smote_cap=3000,
               only=["C_xgboost"])
    assert out2["results"]["C_xgboost"]["test"]["pr_auc"] == pytest.approx(out["results"]["C_xgboost"]["test"]["pr_auc"])
