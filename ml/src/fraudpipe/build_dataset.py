"""
Build the offline benchmark dataset: load -> profile -> engineer features (point-in-time) ->
time-aware split -> fit preprocessing on train only -> save everything reproducibly.

    cd ml/src
    python -m fraudpipe.build_dataset --input ../data/raw/PS_20174392719_1491204439457_log.csv \
        --out ../data/processed/paysim-v1 --seed 42

Optional: --max-rows N (quick smoke run; NOT a valid benchmark, recorded in dataset_meta.json).
"""
from __future__ import annotations

import argparse
import json
import platform
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from . import datasets
from .docs import dataset_card_md
from .features import CATEGORICAL_FEATURES, FEATURE_VERSION, FeatureEngine, Txn
from .preprocess import Preprocessor
from .split import time_split


def engineer(df: pd.DataFrame, engine: FeatureEngine) -> pd.DataFrame:
    """Run the SAME engine used at inference over the time-sorted frame."""
    rows = []
    for ts, uid, cid, amt, typ, lab in zip(df["ts"].to_numpy(), df["user_id"].to_numpy(),
                                           df["counterparty_id"].to_numpy(), df["amount"].to_numpy(),
                                           df["txn_type"].to_numpy(), df["is_fraud"].to_numpy()):
        rows.append(engine.process(Txn(float(ts), uid, cid, float(amt), typ), int(lab)))
    feats = pd.DataFrame(rows)
    return feats[engine.feature_names + CATEGORICAL_FEATURES]


def build(input_path: Path, out_dir: Path, seed: int = 42, max_rows: int | None = None,
          label_delay_s: float = 86400, train_frac: float = 0.6, val_frac: float = 0.2) -> dict:
    np.random.seed(seed)   # pipeline is deterministic; seed is recorded for the model-training stage
    out_dir.mkdir(parents=True, exist_ok=True)
    df = datasets.load_paysim(input_path, max_rows=max_rows)
    prof = datasets.profile(df)

    engine = FeatureEngine(groups=("core",), label_delay_s=label_delay_s,
                           prior_fraud_rate=float(df["is_fraud"].iloc[: int(len(df) * train_frac)].mean()))
    # NOTE: prior_fraud_rate above is computed from the TRAIN portion only (first train_frac of rows in time).
    feats = engineer(df, engine)
    tr, va, te, cuts = time_split(df, train_frac, val_frac)

    pre = Preprocessor(engine.feature_names).fit(feats[tr])
    y = df["is_fraud"].to_numpy()
    split_stats = {}
    for name, mask in (("train", tr), ("val", va), ("test", te)):
        part = feats[mask].copy()
        part.insert(0, "ts", df["ts"].to_numpy()[mask])
        part["is_fraud"] = y[mask]
        part.to_csv(out_dir / f"features_{name}.csv.gz", index=False)
        split_stats[name] = {"rows": int(mask.sum()), "fraud": int(y[mask].sum()),
                             "fraud_rate": float(y[mask].mean()) if mask.any() else None}

    joblib.dump(pre, out_dir / "preprocessor.joblib")
    schema = {"feature_version": FEATURE_VERSION, "engine_params": engine.params(),
              "numeric_features": engine.feature_names, "categorical_features": CATEGORICAL_FEATURES,
              "categories": pre.categories, "output_columns": pre.output_columns,
              "medians": pre.medians}
    meta = {
        "dataset": "PaySim", "source_file": input_path.name,
        "source_sha256": datasets.sha256_file(input_path), "max_rows": max_rows,
        "is_full_benchmark": max_rows is None, "seed": seed,
        "dropped_columns": datasets.PAYSIM_DROPPED, "label_delay_s": label_delay_s,
        "split": {"method": "chronological on timestamp", "train_frac": train_frac,
                  "val_frac": val_frac, **cuts, "stats": split_stats},
        "profile": prof,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "pandas": pd.__version__,
    }
    (out_dir / "feature_schema.json").write_text(json.dumps(schema, indent=2))
    (out_dir / "dataset_meta.json").write_text(json.dumps(meta, indent=2))
    (out_dir / "dataset_card.md").write_text(dataset_card_md(meta))
    return meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-rows", type=int, default=None)
    ap.add_argument("--label-delay-hours", type=float, default=24.0)
    a = ap.parse_args()
    meta = build(a.input, a.out, a.seed, a.max_rows, a.label_delay_hours * 3600)
    print(json.dumps({k: meta[k] for k in ("is_full_benchmark", "split")}, indent=2))


if __name__ == "__main__":
    main()
