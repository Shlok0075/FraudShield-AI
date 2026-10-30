"""Train the behavioral live-stream FraudShield model.

This model is intentionally separate from the legacy anonymized V1-V28 model.
It uses the same fraudpipe.FeatureEngine used by live inference, including
core + device/geo features, then trains XGBoost + Isolation Forest and tunes
the hybrid risk weights on a chronological validation split.

The generated dataset is synthetic and is explicitly labelled as such.
Replace it with a licensed real/suitable dataset when available without
changing the feature/inference contract.
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import average_precision_score, precision_recall_fscore_support, roc_auc_score
from xgboost import XGBClassifier

from fraudpipe.features import CATEGORICAL_FEATURES, FeatureEngine, Txn
from fraudpipe.metrics import CostMatrix, select_thresholds, sweep
from fraudpipe.risk_engine import RiskConfig, behavior_score, evaluate_rules, rule_score

ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "models" / "live-v1"
DATA_DIR = ROOT / "data" / "processed" / "live-v1"
SEED = 42
FEATURES = [
    "amount", "log_amount", "user_txn_count_prior", "is_first_txn",
    "amount_vs_user_avg", "amount_zscore", "txn_count_1m", "txn_count_5m",
    "txn_count_1h", "txn_count_24h", "amount_sum_1h", "amount_sum_24h",
    "time_since_last_txn_s", "account_age_s", "hour_of_day", "day_of_week",
    "is_weekend", "unusual_hour", "counterparty_txn_count_prior",
    "user_fraud_rate_prior", "counterparty_fraud_rate_prior", "new_device",
    "known_device_count", "location_change", "distance_from_prev_km",
    "implied_speed_kmh",
]

LOCATIONS = {
    "Mumbai": (19.0760, 72.8777), "Delhi": (28.6139, 77.2090),
    "Bengaluru": (12.9716, 77.5946), "Pune": (18.5204, 73.8567),
    "Chennai": (13.0827, 80.2707), "Hyderabad": (17.3850, 78.4867),
    "Kolkata": (22.5726, 88.3639), "Ahmedabad": (23.0225, 72.5714),
    "Lagos": (6.5244, 3.3792), "Reykjavik": (64.1466, -21.9426),
}
NORMAL_CITIES = list(LOCATIONS)[:8]
FRAUD_CITIES = ["Lagos", "Reykjavik", "Delhi", "Mumbai"]


def generate_rows(n: int = 60000, seed: int = SEED) -> pd.DataFrame:
    rng = random.Random(seed)
    np_rng = np.random.default_rng(seed)
    users = [f"user-{i:04d}" for i in range(80)]
    merchants = [f"merchant-{i:04d}" for i in range(120)]
    known_devices = {u: [f"{u}-device-0"] for u in users}
    last_city = {u: rng.choice(NORMAL_CITIES) for u in users}
    last_ts = {u: 0.0 for u in users}
    user_avg = {u: rng.uniform(300, 4000) for u in users}
    rows = []
    base_ts = 1_735_689_600.0  # 2025-01-01 UTC
    current_ts = base_ts
    for i in range(n):
        # Mostly advance time; occasionally create a rapid-repeat burst.
        current_ts += rng.choice([5, 10, 30, 60, 120, 300, 900, 1800])
        user = rng.choice(users)
        merchant = rng.choice(merchants)
        prior_dt = current_ts - last_ts[user] if last_ts[user] else 999999.0
        fraud = rng.random() < 0.012
        scenario = "normal"
        amount = max(10.0, float(np_rng.lognormal(math.log(user_avg[user]), 0.65)))
        device = known_devices[user][0]
        city = last_city[user]
        txn_type = rng.choices(["card", "transfer", "cash_out"], weights=[0.65, 0.25, 0.10], k=1)[0]

        if fraud:
            scenario = rng.choice(["high_amount", "new_device", "geo_jump", "burst", "combined"])
            if scenario in ("high_amount", "combined"):
                amount *= rng.uniform(8, 30)
            if scenario in ("new_device", "combined"):
                device = f"{user}-fraud-device-{i}"
            if scenario in ("geo_jump", "combined"):
                city = rng.choice(FRAUD_CITIES)
            if scenario == "burst":
                amount *= rng.uniform(0.05, 0.25)
                # Keep current row close to previous user transaction.
                current_ts = max(current_ts, last_ts[user] + rng.uniform(2, 20))
            if rng.random() < 0.25:
                txn_type = "cash_out"

        # Normal users occasionally change city/device naturally, but at a much lower rate.
        if not fraud and rng.random() < 0.01:
            city = rng.choice(NORMAL_CITIES)
        if not fraud and rng.random() < 0.003:
            device = f"{user}-device-{len(known_devices[user])}"
            known_devices[user].append(device)

        lat, lon = LOCATIONS[city]
        # Small location noise makes repeated city values realistic while preserving distance jumps.
        lat += float(np_rng.normal(0, 0.015))
        lon += float(np_rng.normal(0, 0.015))
        rows.append({
            "ts": current_ts, "user_id": user, "counterparty_id": merchant,
            "amount": round(amount, 2), "txn_type": txn_type, "device_id": device,
            "lat": lat, "lon": lon, "is_fraud": int(fraud), "scenario": scenario,
        })
        last_ts[user] = current_ts
        last_city[user] = city
        # Slow adaptation of the user's normal amount.
        user_avg[user] = 0.98 * user_avg[user] + 0.02 * min(amount, user_avg[user] * 3)
    return pd.DataFrame(rows).sort_values("ts", kind="stable").reset_index(drop=True)


def engineer(df: pd.DataFrame) -> pd.DataFrame:
    engine = FeatureEngine(groups=("core", "device_geo"), label_delay_s=86400, prior_fraud_rate=0.012)
    out = []
    for r in df.to_dict("records"):
        t = Txn(float(r["ts"]), str(r["user_id"]), str(r["counterparty_id"]), float(r["amount"]),
                r["txn_type"], r["device_id"], float(r["lat"]), float(r["lon"]))
        out.append(engine.process(t, int(r["is_fraud"])))
    return pd.DataFrame(out)[FEATURES]


def fit_matrix(train, val, test):
    med = train[FEATURES].astype(float).median().fillna(0.0)
    def transform(df):
        return df[FEATURES].astype(float).replace([np.inf, -np.inf], np.nan).fillna(med).to_numpy()
    return transform(train), transform(val), transform(test), med.to_dict()


def signal_arrays(df: pd.DataFrame, anomaly_model, lo, hi):
    X = df[FEATURES].astype(float).replace([np.inf, -np.inf], np.nan).fillna(0.0).to_numpy()
    raw = -anomaly_model.score_samples(X)
    anomaly = np.clip((raw - lo) / max(hi - lo, 1e-9), 0, 1)
    behavior = np.array([behavior_score(r) for r in df.to_dict("records")])
    rules = np.array([rule_score(evaluate_rules(r, RiskConfig().rules)) for r in df.to_dict("records")])
    return anomaly, behavior, rules


def tune_weights(y, sigs, cost=CostMatrix()):
    names = ["ml", "anomaly", "behavior", "rules"]
    best = None
    for a in range(11):
        for b in range(11-a):
            for c in range(11-a-b):
                d = 10-a-b-c
                w = {"ml": a/10, "anomaly": b/10, "behavior": c/10, "rules": d/10}
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
    MODEL_DIR.mkdir(parents=True, exist_ok=True); DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = generate_rows()
    feats = engineer(df)
    n = len(df); a = int(n*0.6); b = int(n*0.8)
    tr, va, te = df.iloc[:a], df.iloc[a:b], df.iloc[b:]
    ftr, fva, fte = feats.iloc[:a], feats.iloc[a:b], feats.iloc[b:]
    ytr, yva, yte = tr.is_fraud.to_numpy(), va.is_fraud.to_numpy(), te.is_fraud.to_numpy()
    Xtr, Xva, Xte, medians = fit_matrix(ftr, fva, fte)
    scale_pos = float((ytr == 0).sum() / max(1, (ytr == 1).sum()))
    model = XGBClassifier(n_estimators=260, max_depth=6, learning_rate=0.08,
                          subsample=0.9, colsample_bytree=0.9, min_child_weight=2,
                          scale_pos_weight=scale_pos, eval_metric="aucpr", random_state=SEED,
                          n_jobs=-1)
    model.fit(Xtr, ytr)
    ml_tr, ml_va, ml_te = model.predict_proba(Xtr)[:,1], model.predict_proba(Xva)[:,1], model.predict_proba(Xte)[:,1]
    legit = Xtr[ytr == 0]
    iso = IsolationForest(n_estimators=180, contamination="auto", random_state=SEED, n_jobs=-1).fit(legit)
    raw_tr = -iso.score_samples(Xtr); lo, hi = float(np.percentile(raw_tr,1)), float(np.percentile(raw_tr,99.9))
    def an(X): return np.clip((-iso.score_samples(X)-lo)/max(hi-lo,1e-9),0,1)
    an_tr, an_va, an_te = an(Xtr), an(Xva), an(Xte)
    # behavior/rules are based on raw engineered rows.
    _, beh_va, rule_va = signal_arrays(fva, iso, lo, hi)
    _, beh_te, rule_te = signal_arrays(fte, iso, lo, hi)
    weights, review, block = tune_weights(yva, {"ml":ml_va,"anomaly":an_va,"behavior":beh_va,"rules":rule_va})
    cfg = RiskConfig(weights=weights, review_threshold=review, block_threshold=block,
                     provenance="tuned on synthetic live-stream validation split (seed=42); replace/re-tune when using real data")
    cfg.validate()
    test_score = sum(weights[k]*v for k,v in {"ml":ml_te,"anomaly":an_te,"behavior":beh_te,"rules":rule_te}.items())
    # Test metrics at tuned review/block thresholds.
    def m(th):
        pred = test_score >= th
        p,r,f,_ = precision_recall_fscore_support(yte,pred,average="binary",zero_division=0)
        return {"precision":float(p),"recall":float(r),"f1":float(f),"threshold":float(th)}
    metrics={"pr_auc":float(average_precision_score(yte,test_score)),"roc_auc":float(roc_auc_score(yte,test_score)),
             "review":m(review/100),"block":m(block/100),"fraud_test":int(yte.sum()),"test_rows":len(yte)}
    joblib.dump(model, MODEL_DIR/"supervised.joblib"); joblib.dump(iso, MODEL_DIR/"isolation_forest.joblib")
    (MODEL_DIR/"preprocessor.json").write_text(json.dumps({"feature_columns":FEATURES,"medians":medians},indent=2))
    (MODEL_DIR/"risk_config.json").write_text(cfg.to_json())
    metadata={"version":"live-hybrid-v1","algorithm":"XGBoost + IsolationForest + behavior + rules",
              "feature_version":"v1","feature_columns":FEATURES,"dataset":"synthetic live behavioral stream",
              "seed":SEED,"rows":n,"split":{"train":a,"validation":b-a,"test":n-b},
              "metrics":metrics,"scale_pos_weight":scale_pos,"weights":weights,
              "review_threshold":review,"block_threshold":block,"anomaly_score_low":lo,"anomaly_score_high":hi,
              "trained_at":datetime.now(timezone.utc).isoformat(),
              "disclaimer":"Academic prototype. Synthetic training data; not production banking performance."}
    (MODEL_DIR/"metadata.json").write_text(json.dumps(metadata,indent=2))
    # Save a compact benchmark, not the entire raw stream.
    df.to_csv(DATA_DIR/"synthetic_live_stream.csv.gz",index=False,compression="gzip")
    feats.assign(is_fraud=df.is_fraud.to_numpy()).to_csv(DATA_DIR/"features.csv.gz",index=False,compression="gzip")
    print(json.dumps(metadata,indent=2))

if __name__ == "__main__": main()
