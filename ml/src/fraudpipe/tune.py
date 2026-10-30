"""Select hybrid weights + review/block thresholds on VALIDATION data, then evaluate the test set once.

Procedure (documented for the report):
  1. Compute the four signals for every val/test row (ML prob, Isolation-Forest score, behavior, rules).
  2. Enumerate every non-negative weight vector on a 0.1 grid that sums to 1 (286 candidates for 4 signals),
     plus each single-signal config. Score val with each; rank by VAL PR-AUC (ties -> lower val cost).
  3. Choose review/block thresholds on the winner's val scores: review = High-Recall-mode threshold,
     block = High-Precision-mode threshold (block >= review enforced).
  4. Evaluate test ONCE: single signals vs hybrid, at the val-chosen thresholds.
The grid is coarse and chosen on one validation period - report it as such; it is not a proof of generalisation.
"""
from __future__ import annotations

import itertools
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .experiments import load_split
from .metrics import CostMatrix, metrics_at, select_thresholds, sweep, threshold_free
from .risk_engine import SIGNALS, RiskConfig, behavior_score, evaluate_rules, rule_score

STEP = 0.1


def rule_behavior_arrays(df: pd.DataFrame, cfg: RiskConfig) -> tuple[np.ndarray, np.ndarray]:
    rs, bs = np.empty(len(df)), np.empty(len(df))
    for i, row in enumerate(df.to_dict("records")):
        rs[i] = rule_score(evaluate_rules(row, cfg.rules))
        bs[i] = behavior_score(row, cfg.behavior_min_history)
    return rs, bs


def combine(signals: dict[str, np.ndarray], w: dict) -> np.ndarray:
    tot = sum(w.values())
    return sum(w[k] * signals[k] for k in w if w[k] > 0) / tot


def weight_grid(names=SIGNALS, step: float = STEP):
    n = int(round(1 / step))
    for combo in itertools.product(range(n + 1), repeat=len(names)):
        if sum(combo) == n:
            yield {k: c * step for k, c in zip(names, combo)}


def tune(sig_val: dict, y_val, cost: CostMatrix = CostMatrix(), base: RiskConfig | None = None) -> tuple[RiskConfig, pd.DataFrame]:
    names = [k for k in SIGNALS if k in sig_val]
    rows = []
    for w in weight_grid(names):
        s = combine(sig_val, w)
        best_cost = min(r["cost"] for r in sweep(y_val, s, cost))
        rows.append({**{f"w_{k}": round(w[k], 2) for k in names},
                     "val_pr_auc": threshold_free(y_val, s)["pr_auc"], "val_min_cost": best_cost,
                     "single_signal": sum(v > 0 for v in w.values()) == 1})
    table = pd.DataFrame(rows).sort_values(["val_pr_auc", "val_min_cost"], ascending=[False, True]).reset_index(drop=True)
    top = table.iloc[0]
    w = {k: float(top[f"w_{k}"]) for k in names}
    s = combine(sig_val, w)
    th = select_thresholds(sweep(y_val, s, cost))
    review = round(th["high_recall"] * 100, 2)
    block = max(round(th["high_precision"] * 100, 2), review)
    cfg = base or RiskConfig()
    cfg.weights, cfg.review_threshold, cfg.block_threshold = w, review, block
    cfg.provenance = f"tuned on validation: max PR-AUC over 0.1-grid weights; cost matrix {cost.__dict__}"
    cfg.validate()
    return cfg, table


def evaluate_configs(sig: dict, y, cfg: RiskConfig, cost: CostMatrix) -> dict:
    """Single-signal vs tuned hybrid at the tuned thresholds (score/100 scale)."""
    out = {}
    hyb = combine(sig, cfg.weights)
    for name, s in [(k, sig[k]) for k in sig] + [("hybrid", hyb)]:
        r = threshold_free(y, s)
        if name == "hybrid":
            for tname, t in (("review", cfg.review_threshold / 100), ("block", cfg.block_threshold / 100)):
                r[tname] = metrics_at(y, s, t, cost)
        else:  # single signals: own val-independent comparison at the same review/block cut-offs is not meaningful
            r["note"] = "threshold-free metrics only"
        out[name] = r
    return out


def main():
    import argparse
    from .experiments import model_specs  # noqa: F401  (ensures xgboost etc. importable early)
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--experiments", required=True, type=Path)
    ap.add_argument("--model", default=None, help="supervised model name; default = best val PR-AUC")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--fp-cost", type=float, default=5.0)
    ap.add_argument("--fn-cost", type=float, default=500.0)
    a = ap.parse_args()
    cost = CostMatrix(a.fp_cost, a.fn_cost)
    res = json.loads((a.experiments / "experiment_results.json").read_text())["results"]
    sup = {k: v for k, v in res.items() if v["kind"] == "supervised"}
    name = a.model or max(sup, key=lambda k: sup[k]["val"]["pr_auc"])
    pre = joblib.load(a.data / "preprocessor.joblib")
    model = joblib.load(a.experiments / f"{name}.joblib")
    iso = joblib.load(a.experiments / "F_isolation_forest.joblib")
    cfg0 = RiskConfig()
    sigs, ys = {}, {}
    for split in ("val", "test"):
        df = load_split(a.data, split)
        ys[split] = df["is_fraud"].to_numpy()
        Xm = pre.transform(df, scale=sup[name]["scaled_inputs"])
        Xu = pre.transform(df)
        rs, bs = rule_behavior_arrays(df, cfg0)
        an = np.clip((-iso["model"].score_samples(Xu) - iso["lo"]) / (iso["hi"] - iso["lo"]), 0, 1)
        sigs[split] = {"ml": model.predict_proba(Xm)[:, 1], "anomaly": an, "behavior": bs, "rules": rs}
    cfg, table = tune(sigs["val"], ys["val"], cost, cfg0)
    a.out.mkdir(parents=True, exist_ok=True)
    (a.out / "hybrid_config.json").write_text(cfg.to_json())
    table.to_csv(a.out / "weight_search_val.csv", index=False)
    report = {"supervised_model": name, "cost_matrix": cost.__dict__, "weights": cfg.weights,
              "review_threshold": cfg.review_threshold, "block_threshold": cfg.block_threshold,
              "val": evaluate_configs(sigs["val"], ys["val"], cfg, cost),
              "test": evaluate_configs(sigs["test"], ys["test"], cfg, cost),
              "rule_fire_rate_test": float((sigs["test"]["rules"] > 0).mean())}
    (a.out / "hybrid_results.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ("supervised_model", "weights", "review_threshold", "block_threshold",
                                              "rule_fire_rate_test")}, indent=2))
    print({k: round(v["pr_auc"], 4) for k, v in report["test"].items()})


if __name__ == "__main__":
    main()
