"""Dataset adapters + profiling. Currently: PaySim (Lopez-Rojas et al., Kaggle 'ealaxi/paysim1')."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

PAYSIM_REQUIRED = ["step", "type", "amount", "nameOrig", "nameDest", "isFraud"]
# 2024-01-01 00:00 UTC is a Monday. PaySim's `step` is "1 hour of simulated time"; the calendar
# alignment is an ASSUMPTION so hour_of_day / day_of_week are simulated-clock values.
PAYSIM_EPOCH = 1_704_067_200
# Dropped BY DEFAULT: PaySim's balance columns are simulator artefacts (fraud rows leave the
# balance arithmetic inconsistent and drain the sender), which makes the benchmark trivially easy.
# In a real bank these balances ARE known at scoring time, so build_dataset --balance keeps them
# as the optional "balance" feature group. isFlaggedFraud is the output of a rule system and is
# always dropped.
PAYSIM_DROPPED = ["oldbalanceOrg", "newbalanceOrig", "oldbalanceDest", "newbalanceDest", "isFlaggedFraud"]

BALANCE_COLUMNS = ["old_org", "new_org", "old_dest", "new_dest"]
STD_COLUMNS = ["ts", "user_id", "counterparty_id", "amount", "txn_type", "is_fraud"]


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def load_paysim(path: str | Path, max_rows: int | None = None, include_balances: bool = False) -> pd.DataFrame:
    """Load PaySim CSV -> standard frame sorted by time (stable, so original row order breaks ties)."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Download PaySim (see ml/data/raw/README.md) and place the CSV there.")
    raw = pd.read_csv(path, nrows=max_rows)
    missing = [c for c in PAYSIM_REQUIRED if c not in raw.columns]
    if missing:
        raise ValueError(f"not a PaySim file, missing columns: {missing}")
    df = pd.DataFrame({
        "ts": PAYSIM_EPOCH + raw["step"].astype("int64") * 3600,
        "user_id": raw["nameOrig"].astype(str),
        "counterparty_id": raw["nameDest"].astype(str),
        "amount": raw["amount"].astype("float64"),
        "txn_type": raw["type"].astype(str),
        "is_fraud": raw["isFraud"].astype("int8"),
    })
    if include_balances:
        for out, src in (("old_org", "oldbalanceOrg"), ("new_org", "newbalanceOrig"),
                         ("old_dest", "oldbalanceDest"), ("new_dest", "newbalanceDest")):
            df[out] = raw[src].astype("float64")
    if df["amount"].lt(0).any():
        raise ValueError("negative amounts found")
    cols = STD_COLUMNS + (BALANCE_COLUMNS if include_balances else [])
    return df.sort_values("ts", kind="stable").reset_index(drop=True)[cols]


def profile(df: pd.DataFrame) -> dict:
    """Numbers for the dataset card - always recomputed from the data, never typed by hand."""
    per_user = df.groupby("user_id").size()
    per_cp = df.groupby("counterparty_id").size()
    by_type = df.groupby("txn_type")["is_fraud"].agg(["size", "sum"])
    return {
        "rows": int(len(df)),
        "fraud_rows": int(df["is_fraud"].sum()),
        "fraud_rate": float(df["is_fraud"].mean()),
        "missing_values": {c: int(v) for c, v in df.isna().sum().items()},
        "duplicate_rows": int(df.duplicated().sum()),
        "unique_users": int(per_user.size),
        "share_users_with_more_than_1_txn": float((per_user > 1).mean()),
        "max_txns_per_user": int(per_user.max()),
        "unique_counterparties": int(per_cp.size),
        "share_counterparties_with_more_than_1_txn": float((per_cp > 1).mean()),
        "time_span_hours": float((df["ts"].max() - df["ts"].min()) / 3600),
        "fraud_by_type": {t: {"rows": int(r["size"]), "fraud": int(r["sum"])} for t, r in by_type.iterrows()},
    }
