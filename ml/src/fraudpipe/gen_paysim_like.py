"""Generate a tiny PaySim-FORMAT csv (same columns) for tests / smoke runs ONLY.
It is not PaySim and any metric computed on it is meaningless."""
import numpy as np
import pandas as pd


def make_paysim_like(n: int = 5000, seed: int = 0, n_users: int = 800) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    step = np.sort(rng.integers(1, 200, n))
    typ = rng.choice(["PAYMENT", "TRANSFER", "CASH_OUT", "CASH_IN", "DEBIT"], n, p=[.4, .1, .3, .15, .05])
    amount = np.round(rng.lognormal(6, 1.2, n), 2)
    fraud = ((np.isin(typ, ["TRANSFER", "CASH_OUT"])) & (rng.random(n) < 0.03)).astype(int)
    amount = np.where(fraud == 1, amount * 8, amount)
    return pd.DataFrame({
        "step": step, "type": typ, "amount": amount,
        "nameOrig": ["C%d" % i for i in rng.integers(0, n_users, n)],
        "oldbalanceOrg": 0.0, "newbalanceOrig": 0.0,
        "nameDest": [("M%d" if t == "PAYMENT" else "C%d") % i for t, i in zip(typ, rng.integers(0, 300, n))],
        "oldbalanceDest": 0.0, "newbalanceDest": 0.0, "isFraud": fraud, "isFlaggedFraud": 0})
