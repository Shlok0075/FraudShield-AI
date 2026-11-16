"""
Train the live-v1 hybrid model on the PaySim 6M processed features.

Replaces the synthetic-data live model with a model trained on the full
PaySim benchmark (6,362,620 rows, 8,213 fraud, 0.129%).

Outputs to ml/models/live-v1/:
  supervised.joblib   - XGBoost classifier
  isolation_forest.joblib - Isolation Forest (trained on legit rows only)
  preprocessor.json   - feature columns + medians
  risk_config.json    - tuned RiskConfig (weights + thresholds)
  metadata.json       - model metadata + metrics

Run:  python ml/src/train_live_paysim.py
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score
from xgboost import XGBClassifier

SRC = Path(__file__).resolve().parent
sys_path = str(SRC)
import sys
if sys_path not in sys.path:
    sys.path.insert(0, sys_path)

from fraudpipe.features import CATEGORICAL_FEATURES, FeatureEngine, Txn  # noqa: E402
from fraudpipe.metrics import CostMatrix, select_thresholds, sweep  # noqa: E402
from fraudpipe.risk_engine import RiskConfig, behavior_score, evaluate_rules, rule_score  # noqa: E402

DATA_DIR = SRC.parent / "data" / "processed" / "paysim-v1"
MODEL_DIR = SRC.parent / "models" / "live-v1"
SEED = 42

# Feature columns the live model serves (matching predict.py / feature_engineering.py)
# Paysim-v1 features + device_geo fields (default to 0 at inference since paysim has no device/geo)
LIVE_FEATURES = [
    "amount", "log_amount", "user_txn_count_prior", "is_first_txn",
    "amount_vs_user_avg", "amount_zscore", "txn_count_1m", "txn_count_5m",
    "txn_count_1h", "txn_count_24h", "amount_sum_1h", "amount_sum_24h",
    "time_since_last_txn_s", "account_age_s", "hour_of_day", "day_of_week",
    "is_weekend", "unusual_hour", "counterparty_txn_count_prior",
    "user_fraud_rate_prior", "counterparty_fraud_rate_prior",
    # device_geo fields (not in paysim; default 0 at inference)
    "new_device", "known_device_count", "location_change", "distance_from_prev_km",
    "implied_speed_kmh",
    # txn_type one-hot from paysim
    "txn_type=CASH_IN", "txn_type=CASH_OUT", "txn_type=DEBIT", "txn_type=PAYMENT", "txn_type=TRANSFER",
]


def load_features(data_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    tr = pd.read_csv(data_dir / "features_train.csv.gz")
    va = pd.read_csv(data_dir / "features_val.csv.gz")
    te = pd.read_csv(data_dir / "features_test.csv.gz")
    return tr, va, te


def align_columns(df: pd.DataFrame, feature_columns: list[str], medians: dict) -> pd.DataFrame:
    """Ensure df has exactly the feature_columns, filling missing with medians."""
    out = pd.DataFrame(index=df.index)
    for col in feature_columns:
        if col in df.columns:
            out[col] = df[col]
        else:
            out[col] = medians.get(col, 0.0)
    # Fill any NaN
    out = out.fillna(medians)
    return out


def fit_medians(train_df: pd.DataFrame, feature_columns: list[str]) -> dict:
    medians = {}
    for col in feature_columns:
        if col in train_df.columns:
            medians[col] = float(train_df[col].median())
        else:
            medians[col] = 0.0
    return medians


def transform(df: pd.DataFrame, feature_columns: list[str], medians: dict) -> np.ndarray:
    out = align_columns(df, feature_columns, medians)
    return out[feature_columns].to_numpy(dtype=float)


def _clip01(x):
    return np.clip(x, 0.0, 1.0)


def behavior_score_vectorized(df: pd.DataFrame, min_history: int = 5) -> np.ndarray:
    """Vectorized behavior score (replaces row-by-row behavior_score)."""
    conf = _clip01(df["user_txn_count_prior"].to_numpy(dtype=float) / float(min_history))
    parts_v, parts_w = [], []

    if "amount_vs_user_avg" in df.columns:
        avg = df["amount_vs_user_avg"].to_numpy(dtype=float)
        v = conf * _clip01(np.log(np.maximum(avg, 1.0)) / math.log(10.0)) * 0.30
        parts_v.append(v); parts_w.append(0.30)

    if "amount_zscore" in df.columns:
        z = df["amount_zscore"].to_numpy(dtype=float)
        v = conf * _clip01(z / 5.0) * 0.20
        parts_v.append(v); parts_w.append(0.20)

    if "txn_count_5m" in df.columns:
        v = _clip01(df["txn_count_5m"].to_numpy(dtype=float) / 5.0) * 0.15
        parts_v.append(v); parts_w.append(0.15)

    if "unusual_hour" in df.columns:
        v = df["unusual_hour"].to_numpy(dtype=float) * 0.05
        parts_v.append(v); parts_w.append(0.05)

    if "new_device" in df.columns and "known_device_count" in df.columns:
        nd = df["new_device"].to_numpy(dtype=float)
        kd = df["known_device_count"].to_numpy(dtype=float)
        v = nd * np.where(kd > 0, 1.0, 0.3) * 0.15
        parts_v.append(v); parts_w.append(0.15)

    if "location_change" in df.columns:
        v = df["location_change"].to_numpy(dtype=float) * 0.15
        parts_v.append(v); parts_w.append(0.15)

    tot = sum(parts_w)
    if tot <= 0:
        return np.zeros(len(df), dtype=float)
    num = sum(v * w for v, w in zip(parts_v, parts_w))
    return _clip01(num / tot)


def rules_score_vectorized(df: pd.DataFrame, rc=None) -> np.ndarray:
    """Vectorized rule score (replaces row-by-row evaluate_rules + rule_score)."""
    if rc is None:
        rc = RiskConfig().rules
    n = df["user_txn_count_prior"].to_numpy(dtype=float) if "user_txn_count_prior" in df.columns else np.zeros(len(df))

    points = np.zeros(len(df), dtype=float)

    # impossible_velocity: implied_speed_kmh > 900 → 0.9
    if "implied_speed_kmh" in df.columns:
        mask = df["implied_speed_kmh"].to_numpy(dtype=float) > rc.max_speed_kmh
        points = np.where(mask, points + rc.points["impossible_velocity"], points)

    # extreme_amount_deviation: n>=5 AND (avg>=8 OR zscore>=4) → 0.5
    if "amount_vs_user_avg" in df.columns or "amount_zscore" in df.columns:
        avg_ok = df["amount_vs_user_avg"].to_numpy(dtype=float) >= rc.amount_ratio if "amount_vs_user_avg" in df.columns else np.zeros(len(df), dtype=bool)
        z_ok = df["amount_zscore"].to_numpy(dtype=float) >= rc.amount_zscore if "amount_zscore" in df.columns else np.zeros(len(df), dtype=bool)
        mask = (n >= rc.min_history) & (avg_ok | z_ok)
        points = np.where(mask, points + rc.points["extreme_amount_deviation"], points)

    # new_device_and_location_change → 0.6
    if "new_device" in df.columns and "location_change" in df.columns:
        mask = (df["new_device"].to_numpy(dtype=float) == 1) & (df["location_change"].to_numpy(dtype=float) == 1)
        points = np.where(mask, points + rc.points["new_device_and_location_change"], points)

    # card_testing: txn_count_5m>=3 AND n>=1 AND avg<=0.3 → 0.6
    if "txn_count_5m" in df.columns and "amount_vs_user_avg" in df.columns:
        mask = (df["txn_count_5m"].to_numpy(dtype=float) >= rc.card_test_count_5m) & (n >= 1) & \
               (df["amount_vs_user_avg"].to_numpy(dtype=float) <= rc.card_test_max_ratio)
        points = np.where(mask, points + rc.points["card_testing"], points)

    # transaction_burst: txn_count_1m>=5 OR txn_count_1h>=15 → 0.5
    burst = np.zeros(len(df), dtype=bool)
    if "txn_count_1m" in df.columns:
        burst |= df["txn_count_1m"].to_numpy(dtype=float) >= rc.burst_1m
    if "txn_count_1h" in df.columns:
        burst |= df["txn_count_1h"].to_numpy(dtype=float) >= rc.burst_1h
    points = np.where(burst, points + rc.points["transaction_burst"], points)

    # suspicious_counterparty: counterparty_fraud_rate_prior>=0.05 → 0.5
    if "counterparty_fraud_rate_prior" in df.columns:
        mask = df["counterparty_fraud_rate_prior"].to_numpy(dtype=float) >= rc.merchant_fraud_rate
        points = np.where(mask, points + rc.points["suspicious_counterparty"], points)

    # unusual_hour_high_amount: unusual_hour==1 AND avg>=3 AND n>=1 → 0.3
    if "unusual_hour" in df.columns and "amount_vs_user_avg" in df.columns:
        mask = (df["unusual_hour"].to_numpy(dtype=float) == 1) & \
               (df["amount_vs_user_avg"].to_numpy(dtype=float) >= rc.unusual_hour_ratio) & (n >= 1)
        points = np.where(mask, points + rc.points["unusual_hour_high_amount"], points)

    return _clip01(points)


def signal_arrays(df: pd.DataFrame, X_num: np.ndarray, anomaly_model, lo: float, hi: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    raw = -anomaly_model.score_samples(X_num)
    anomaly = np.clip((raw - lo) / max(hi - lo, 1e-9), 0, 1)
    behavior = behavior_score_vectorized(df)
    rules = rules_score_vectorized(df)
    return anomaly, behavior, rules


def tune_weights(y, sigs, cost=CostMatrix()):
    names = ["ml", "anomaly", "behavior", "rules"]
    best = None
    for a in range(11):
        for b in range(11 - a):
            for c in range(11 - a - b):
                d = 10 - a - b - c
                w = {"ml": a / 10, "anomaly": b / 10, "behavior": c / 10, "rules": d / 10}
                score = sum(w[k] * sigs[k] for k in names)
                pr = average_precision_score(y, score)
                min_cost = min(r["cost"] for r in sweep(y, score, cost))
                key = (pr, -min_cost)
                if best is None or key > best[0]:
                    best = (key, w, score)
    thresholds = select_thresholds(sweep(y, best[2], cost))
    review = max(0.0, min(100.0, thresholds["high_recall"] * 100))
    block = max(review, min(100.0, thresholds["high_precision"] * 100))
    return best[1], review, block


def main():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/6] Loading PaySim-v1 processed features...")
    tr, va, te = load_features(DATA_DIR)
    y_tr, y_va, y_te = tr["is_fraud"].to_numpy(), va["is_fraud"].to_numpy(), te["is_fraud"].to_numpy()
    print(f"    train={len(tr)} ({y_tr.sum()} fraud), val={len(va)} ({y_va.sum()} fraud), "
          f"test={len(te)} ({y_te.sum()} fraud)")

    print("[2/6] Fitting medians + aligning columns...")
    medians = fit_medians(tr, LIVE_FEATURES)
    X_tr = transform(tr, LIVE_FEATURES, medians)
    X_va = transform(va, LIVE_FEATURES, medians)
    X_te = transform(te, LIVE_FEATURES, medians)

    print("[3/6] Training XGBoost + Isolation Forest...")
    scale_pos = float((y_tr == 0).sum() / max(1, (y_tr == 1).sum()))
    # Cap legit rows for Isolation Forest (3.8M legit rows is too slow)
    legit_idx = np.flatnonzero(y_tr == 0)
    rng = np.random.default_rng(SEED)
    legit_sample = np.sort(rng.choice(legit_idx, min(200_000, len(legit_idx)), replace=False))
    X_legit = X_tr[legit_sample]

    xgb = XGBClassifier(
        n_estimators=120, max_depth=6, learning_rate=0.08,
        subsample=0.9, colsample_bytree=0.9, min_child_weight=2,
        scale_pos_weight=scale_pos, eval_metric="aucpr",
        random_state=SEED, n_jobs=-1, tree_method="hist",
    )
    xgb.fit(X_tr, y_tr)
    ml_va = xgb.predict_proba(X_va)[:, 1]
    ml_te = xgb.predict_proba(X_te)[:, 1]

    iso = IsolationForest(n_estimators=100, contamination="auto", random_state=SEED, n_jobs=-1).fit(X_legit)
    raw_tr = -iso.score_samples(X_tr)
    lo, hi = float(np.percentile(raw_tr, 1)), float(np.percentile(raw_tr, 99.9))

    def an(X_):
        return np.clip((-iso.score_samples(X_) - lo) / max(hi - lo, 1e-9), 0, 1)

    an_va, an_te = an(X_va), an(X_te)

    _, beh_va, rule_va = signal_arrays(va.copy(), X_va, iso, lo, hi)
    _, beh_te, rule_te = signal_arrays(te.copy(), X_te, iso, lo, hi)

    print("[4/6] Tuning hybrid risk weights on validation...")
    weights, review, block = tune_weights(
        y_va, {"ml": ml_va, "anomaly": an_va, "behavior": beh_va, "rules": rule_va}
    )
    cfg = RiskConfig(
        weights=weights, review_threshold=review, block_threshold=block,
        provenance="tuned on PaySim 6M validation split (seed=42)",
    )
    cfg.validate()

    test_score = sum(weights[k] * v for k, v in
                     {"ml": ml_te, "anomaly": an_te, "behavior": beh_te, "rules": rule_te}.items())

    def m(th):
        pred = test_score >= th
        p, r, f, _ = precision_recall_fscore_support(y_te, pred, average="binary", zero_division=0)
        return {"precision": float(p), "recall": float(r), "f1": float(f), "threshold": float(th)}

    metrics = {
        "pr_auc": float(average_precision_score(y_te, test_score)),
        "roc_auc": float(roc_auc_score(y_te, test_score)),
        "review": m(review / 100),
        "block": m(block / 100),
        "fraud_test": int(y_te.sum()),
        "test_rows": int(len(y_te)),
    }

    print("[5/6] Saving model artifacts...")
    joblib.dump(xgb, MODEL_DIR / "supervised.joblib")
    joblib.dump(iso, MODEL_DIR / "isolation_forest.joblib")
    (MODEL_DIR / "preprocessor.json").write_text(
        json.dumps({"feature_columns": LIVE_FEATURES, "medians": medians}, indent=2))
    (MODEL_DIR / "risk_config.json").write_text(cfg.to_json())
    metadata = {
        "version": "live-hybrid-v1",
        "algorithm": "XGBoost + IsolationForest + behavior + rules",
        "feature_version": "v1",
        "feature_columns": LIVE_FEATURES,
        "dataset": "PaySim 6M (PS_20174392719_1491204439457_log.csv)",
        "seed": SEED,
        "rows": int(len(tr) + len(va) + len(te)),
        "split": {"train": int(len(tr)), "validation": int(len(va)), "test": int(len(te))},
        "metrics": metrics,
        "scale_pos_weight": scale_pos,
        "weights": weights,
        "review_threshold": review,
        "block_threshold": block,
        "anomaly_score_low": lo,
        "anomaly_score_high": hi,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": "Academic prototype. Trained on PaySim synthetic data; not production banking performance.",
    }
    (MODEL_DIR / "metadata.json").write_text(json.dumps(metadata, indent=2))

    print("[6/6] Done.")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
