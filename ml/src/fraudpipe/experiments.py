"""
Reproducible model comparison on a dataset built by fraudpipe.build_dataset.

    cd ml/src
    python -m fraudpipe.experiments --data ../data/processed/paysim-v1 \
        --out ../models/experiments/paysim-v1 --seed 42

Models: A LogReg | A2 LogReg+class weight | B RandomForest | B2 RF+class weight | C XGBoost |
        D XGBoost+scale_pos_weight | E XGBoost+SMOTE | F IsolationForest (unsupervised, trained on legit rows only)
Protocol: fit on train -> pick thresholds on val -> evaluate test ONCE at those thresholds.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from imblearn.over_sampling import SMOTE
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.linear_model import LinearRegression, LogisticRegression
from xgboost import XGBClassifier

from .metrics import MODES, CostMatrix, metrics_at, select_thresholds, sweep, threshold_free


def load_split(data_dir: Path, name: str) -> pd.DataFrame:
    return pd.read_csv(data_dir / f"features_{name}.csv.gz")


def cap_negatives(X: pd.DataFrame, y: np.ndarray, cap: int | None, seed: int):
    """Keep ALL fraud rows, randomly down-sample legit rows to `cap` total rows. Recorded in results."""
    if cap is None or len(y) <= cap:
        return X, y
    rng = np.random.default_rng(seed)
    pos = np.flatnonzero(y == 1)
    neg = np.flatnonzero(y == 0)
    keep = np.sort(np.concatenate([pos, rng.choice(neg, max(cap - len(pos), 1), replace=False)]))
    return X.iloc[keep], y[keep]


def model_specs(seed: int, fast: bool = False) -> dict:
    n_est = 40 if fast else 300
    rf_n = 30 if fast else 200
    xgb = dict(n_estimators=n_est, max_depth=6, learning_rate=0.1, subsample=0.8, colsample_bytree=0.8,
               tree_method="hist", eval_metric="aucpr", random_state=seed, n_jobs=-1)
    # (builder(pos_weight) , scale features?, smote?, train-row cap key)
    return {
        "linear_regression": (lambda w: LinearRegression(), True, False, "linear"),
        "A_logreg": (lambda w: LogisticRegression(max_iter=1000, random_state=seed), True, False, "linear"),
        "A2_logreg_class_weight": (lambda w: LogisticRegression(max_iter=1000, class_weight="balanced",
                                                                random_state=seed), True, False, "linear"),
        "B_random_forest": (lambda w: RandomForestClassifier(n_estimators=rf_n, min_samples_leaf=2, n_jobs=-1,
                                                             random_state=seed), False, False, "rf"),
        "B2_random_forest_class_weight": (lambda w: RandomForestClassifier(
            n_estimators=rf_n, min_samples_leaf=2, class_weight="balanced_subsample", n_jobs=-1,
            random_state=seed), False, False, "rf"),
        "C_xgboost": (lambda w: XGBClassifier(**xgb), False, False, "full"),
        "D_xgboost_class_weight": (lambda w: XGBClassifier(scale_pos_weight=w, **xgb), False, False, "full"),
        "E_xgboost_smote": (lambda w: XGBClassifier(**xgb), False, True, "smote"),
    }


def latency_ms(predict_fn, X: pd.DataFrame, n: int = 200) -> dict:
    """Single-row MODEL latency (excludes feature engineering / DB)."""
    rows = [X.iloc[[i]] for i in range(min(n, len(X)))]
    # Warm-up: handle models without predict_proba (LinearRegression)
    try:
        predict_fn(rows[0])
    except AttributeError:
        pass
    times = []
    for r in rows:
        t = time.perf_counter()
        try:
            predict_fn(r)
        except AttributeError:
            # LinearRegression: use predict instead
            pass
        times.append((time.perf_counter() - t) * 1000)
    return {"median_ms": float(np.median(times)), "p95_ms": float(np.percentile(times, 95))}


def evaluate_scores(name, s_val, y_val, s_test, y_test, cost) -> tuple[dict, pd.DataFrame]:
    val_sweep = sweep(y_val, s_val, cost)
    chosen = select_thresholds(val_sweep)
    res = {"val": threshold_free(y_val, s_val), "test": threshold_free(y_test, s_test),
           "thresholds": chosen, "modes": {}}
    for m in MODES:
        t = chosen[m]
        res["modes"][m] = {"threshold": t,
                           "val": metrics_at(y_val, s_val, t, cost),
                           "test": metrics_at(y_test, s_test, t, cost)}      # test evaluated once, at val thresholds
    table = pd.DataFrame(val_sweep)
    table.insert(0, "model", name)
    return res, table


def run(data_dir: Path, out_dir: Path, seed: int = 42, fast: bool = False, cost: CostMatrix = CostMatrix(),
        rf_cap: int | None = 500_000, smote_cap: int | None = 300_000, only: list[str] | None = None) -> dict:
    np.random.seed(seed)
    out_dir.mkdir(parents=True, exist_ok=True)
    pre = joblib.load(data_dir / "preprocessor.joblib")
    meta = json.loads((data_dir / "dataset_meta.json").read_text())
    tr, va, te = (load_split(data_dir, s) for s in ("train", "val", "test"))
    y_tr, y_va, y_te = (d["is_fraud"].to_numpy() for d in (tr, va, te))
    Xu = {k: pre.transform(d) for k, d in (("train", tr), ("val", va), ("test", te))}
    Xs = {k: pre.transform(d, scale=True) for k, d in (("train", tr), ("val", va), ("test", te))}
    caps = {"linear": None, "full": None, "rf": rf_cap, "smote": smote_cap}
    pos_w = float((y_tr == 0).sum() / max((y_tr == 1).sum(), 1))

    results, tables = {}, []
    for name, (build, scaled, smote, capkey) in model_specs(seed, fast).items():
        if only and name not in only:
            continue
        X = Xs if scaled else Xu
        Xtr, ytr = cap_negatives(X["train"], y_tr, caps[capkey], seed)
        if smote:
            Xtr, ytr = SMOTE(random_state=seed).fit_resample(Xtr, ytr)
        t0 = time.perf_counter()
        model = build(pos_w).fit(Xtr, ytr)
        fit_s = time.perf_counter() - t0
        # LinearRegression has no predict_proba; threshold continuous output at 0.5
        if hasattr(model, "predict_proba"):
            pv = model.predict_proba(X["val"])[:, 1]
            pt = model.predict_proba(X["test"])[:, 1]
        else:
            pv = np.clip(model.predict(X["val"]), 0.0, 1.0)
            pt = np.clip(model.predict(X["test"]), 0.0, 1.0)
        res, table = evaluate_scores(name, pv, y_va, pt, y_te, cost)
        # LinearRegression has no predict_proba; use predict for latency measurement
        if hasattr(model, "predict_proba"):
            predict_fn = lambda r, m=model: m.predict_proba(r)
        else:
            predict_fn = lambda r, m=model: m.predict(r)
        res.update(kind="supervised", fit_seconds=fit_s, n_train_used=int(len(ytr)),
                   train_fraud_used=int(ytr.sum()), scaled_inputs=scaled, smote=smote,
                   latency=latency_ms(predict_fn, X["test"]))
        results[name] = res
        tables.append(table)
        joblib.dump(model, out_dir / f"{name}.joblib")

    if not only or "F_isolation_forest" in only:
        legit = Xu["train"][y_tr == 0]
        legit, _ = cap_negatives(legit, np.zeros(len(legit), int), rf_cap, seed)
        t0 = time.perf_counter()
        iso = IsolationForest(n_estimators=50 if fast else 200, random_state=seed, n_jobs=-1).fit(legit)
        fit_s = time.perf_counter() - t0
        raw_tr = -iso.score_samples(Xu["train"])
        lo, hi = float(np.percentile(raw_tr, 1)), float(np.percentile(raw_tr, 99.9))     # fitted on TRAIN only
        norm = lambda X_: np.clip((-iso.score_samples(X_) - lo) / (hi - lo), 0, 1)       # noqa: E731
        res, table = evaluate_scores("F_isolation_forest", norm(Xu["val"]), y_va, norm(Xu["test"]), y_te, cost)
        res.update(kind="unsupervised", fit_seconds=fit_s, n_train_used=int(len(legit)), train_fraud_used=0,
                   note="Anomaly score is an additional risk signal, not a fraud classifier.",
                   latency=latency_ms(lambda r: norm(r), Xu["test"]))
        results["F_isolation_forest"] = res
        tables.append(table)
        joblib.dump({"model": iso, "lo": lo, "hi": hi}, out_dir / "F_isolation_forest.joblib")

    out = {"seed": seed, "fast_mode": fast, "cost_matrix": cost.__dict__,
           "dataset": {k: meta[k] for k in ("dataset", "source_sha256", "is_full_benchmark", "split")},
           "protocol": "fit on train; thresholds selected on validation; test evaluated once at those thresholds",
           "caps": {"rf_train_rows": rf_cap, "smote_train_rows": smote_cap,
                    "note": "capped models keep all fraud rows and down-sample legit rows"},
           "results": results}
    (out_dir / "experiment_results.json").write_text(json.dumps(out, indent=2))
    pd.concat(tables).to_csv(out_dir / "threshold_analysis_val.csv", index=False)
    rows = []
    for n, r in results.items():
        b = r["modes"]["balanced"]["test"]
        rows.append({"model": n, "test_pr_auc": r["test"]["pr_auc"], "test_roc_auc": r["test"]["roc_auc"],
                     "balanced_threshold": r["thresholds"]["balanced"], "precision": b["precision"],
                     "recall": b["recall"], "f1": b["f1"], "fpr": b["fpr"], "fnr": b["fnr"],
                     "tp": b["tp"], "fp": b["fp"], "tn": b["tn"], "fn": b["fn"],
                     "min_cost_test_cost": r["modes"]["min_cost"]["test"]["cost"],
                     "brier": r["test"]["brier"], "latency_median_ms": r["latency"]["median_ms"]})
    pd.DataFrame(rows).sort_values("test_pr_auc", ascending=False).to_csv(out_dir / "model_comparison.csv", index=False)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fast", action="store_true", help="small models for a smoke run")
    ap.add_argument("--fp-cost", type=float, default=5.0)
    ap.add_argument("--fn-cost", type=float, default=500.0)
    ap.add_argument("--only", nargs="*")
    a = ap.parse_args()
    out = run(a.data, a.out, a.seed, a.fast, CostMatrix(a.fp_cost, a.fn_cost), only=a.only)
    print(pd.read_csv(a.out / "model_comparison.csv")[["model", "test_pr_auc", "test_roc_auc", "precision", "recall"]]
          .to_string(index=False))


if __name__ == "__main__":
    main()
