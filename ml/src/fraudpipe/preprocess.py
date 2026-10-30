"""Preprocessing fitted on TRAIN only; persisted with the model so inference applies the identical transform."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import CATEGORICAL_FEATURES


class Preprocessor:
    """Median imputation + fixed one-hot for categoricals + (optional) standardisation.

    scale=False -> tree models (XGBoost / RF / Isolation Forest); scale=True -> Logistic Regression.
    """

    def __init__(self, numeric_cols: list[str]):
        self.numeric_cols = list(numeric_cols)
        self.categories: dict[str, list[str]] = {}
        self.medians: dict[str, float] = {}
        self.means: dict[str, float] = {}
        self.stds: dict[str, float] = {}
        self.fitted = False

    def fit(self, df: pd.DataFrame) -> "Preprocessor":
        for c in CATEGORICAL_FEATURES:
            self.categories[c] = sorted(df[c].dropna().astype(str).unique().tolist())
        num = df[self.numeric_cols].astype("float64")
        self.medians = {c: float(num[c].median()) if num[c].notna().any() else 0.0 for c in self.numeric_cols}
        filled = num.fillna(pd.Series(self.medians))
        self.means = {c: float(filled[c].mean()) for c in self.numeric_cols}
        self.stds = {c: float(filled[c].std(ddof=0)) or 1.0 for c in self.numeric_cols}
        self.fitted = True
        return self

    @property
    def output_columns(self) -> list[str]:
        cols = list(self.numeric_cols)
        for c in CATEGORICAL_FEATURES:
            cols += [f"{c}={v}" for v in self.categories[c]]
        return cols

    def transform(self, df: pd.DataFrame, scale: bool = False) -> pd.DataFrame:
        if not self.fitted:
            raise RuntimeError("Preprocessor not fitted")
        num = df[self.numeric_cols].astype("float64").fillna(pd.Series(self.medians))
        if scale:
            num = (num - pd.Series(self.means)) / pd.Series(self.stds)
        parts = [num]
        for c in CATEGORICAL_FEATURES:
            vals = df[c].astype(str)
            parts.append(pd.DataFrame({f"{c}={v}": (vals == v).astype("float64") for v in self.categories[c]},
                                      index=df.index))
        return pd.concat(parts, axis=1)[self.output_columns]
