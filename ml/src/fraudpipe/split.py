"""Time-aware split: chronological cut-offs, never random."""
from __future__ import annotations

import pandas as pd


def time_split(df: pd.DataFrame, train_frac: float = 0.6, val_frac: float = 0.2):
    """Cut on TIMESTAMP quantiles so no timestamp is shared between two splits. df must be time-sorted."""
    if not (0 < train_frac < 1 and 0 < val_frac < 1 and train_frac + val_frac < 1):
        raise ValueError("fractions must be in (0,1) and sum to < 1")
    if not df["ts"].is_monotonic_increasing:
        raise ValueError("df must be sorted by ts")
    t_cut = df["ts"].iloc[int(len(df) * train_frac)]
    v_cut = df["ts"].iloc[int(len(df) * (train_frac + val_frac))]
    train = df["ts"] < t_cut
    val = (df["ts"] >= t_cut) & (df["ts"] < v_cut)
    test = df["ts"] >= v_cut
    return train.to_numpy(), val.to_numpy(), test.to_numpy(), {"train_end_ts": int(t_cut), "val_end_ts": int(v_cut)}
