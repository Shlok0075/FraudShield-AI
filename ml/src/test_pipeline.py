"""Tests for the fraudpipe data/feature pipeline. Run: cd ml/src && pytest test_pipeline.py -v"""
import numpy as np
import pandas as pd
import pytest

from fraudpipe import datasets
from fraudpipe.build_dataset import build, engineer
from fraudpipe.features import DAY_S, FeatureEngine, Txn, haversine_km
from fraudpipe.gen_paysim_like import make_paysim_like
from fraudpipe.preprocess import Preprocessor
from fraudpipe.split import time_split

T0 = 1_704_067_200  # Monday 00:00 UTC


def tx(ts, user="u1", cp="m1", amount=100.0, **kw):
    return Txn(T0 + ts, user, cp, amount, "PAYMENT", **kw)


def test_first_txn_defaults():
    f = FeatureEngine().features(tx(0))
    assert f["is_first_txn"] == 1 and f["amount_vs_user_avg"] == 1.0 and f["amount_zscore"] == 0.0
    assert f["time_since_last_txn_s"] == 30 * DAY_S and f["day_of_week"] == 0 and f["hour_of_day"] == 0


def test_features_do_not_include_current_txn():
    e = FeatureEngine()
    e.process(tx(0, amount=100))
    e.process(tx(60, amount=300))
    f = e.features(tx(120, amount=200))
    assert f["user_txn_count_prior"] == 2
    assert f["amount_vs_user_avg"] == pytest.approx(200 / 200)
    assert f["txn_count_1m"] == 1 and f["txn_count_5m"] == 2 and f["amount_sum_1h"] == 400


def test_features_is_read_only():
    e = FeatureEngine()
    e.process(tx(0))
    a = e.features(tx(10))
    b = e.features(tx(10))
    assert a == b


def test_future_rows_never_change_past_features():
    base = [tx(i * 600, amount=50 + i) for i in range(30)]
    e1 = FeatureEngine(label_delay_s=3600)
    f1 = [e1.process(t, label=int(i % 7 == 0)) for i, t in enumerate(base)]
    e2 = FeatureEngine(label_delay_s=3600)                       # same history, truncated future
    f2 = [e2.process(t, label=int(i % 7 == 0)) for i, t in enumerate(base[:15])]
    assert f2 == f1[:15]


def test_only_matured_labels_influence_features():
    def run(flip_last):
        e = FeatureEngine(label_delay_s=3600)
        e.process(tx(0), label=1)
        e.process(tx(3000), label=1 if flip_last else 0)          # matures at 6600
        return e.features(tx(4000))                               # only first label matured
    assert run(True) == run(False)


def test_label_delay_blocks_immediate_label_leak():
    e = FeatureEngine(label_delay_s=3600, prior_fraud_rate=0.0, smoothing_m=1)
    e.process(tx(0), label=1)                       # fraud, but label matures at +1h
    early = e.features(tx(1800))                    # 30 min later: label NOT yet usable
    late = e.features(tx(3601))                     # after maturity: usable
    assert early["user_fraud_rate_prior"] == 0.0
    assert late["user_fraud_rate_prior"] == pytest.approx(0.5)
    assert late["counterparty_fraud_rate_prior"] == pytest.approx(0.5)


def test_training_and_inference_paths_produce_identical_features():
    """Streaming over the dataset == warm-start by replay + features() for the next txn."""
    txns = [tx(i * 90, user="a" if i % 3 else "b", amount=20 + (i * 37) % 400) for i in range(60)]
    labels = [int(i % 17 == 0) for i in range(60)]
    train_engine = FeatureEngine(label_delay_s=1800)
    train_feats = [train_engine.process(t, l) for t, l in zip(txns, labels)]
    for k in (5, 30, 59):
        live = FeatureEngine(label_delay_s=1800)
        for t, l in zip(txns[:k], labels[:k]):
            live.update(t, l)                       # history replay
        assert live.features(txns[k]) == train_feats[k]


def test_device_geo_group():
    e = FeatureEngine(groups=("core", "device_geo"))
    e.process(tx(0, device_id="d1", lat=19.07, lon=72.87))          # Mumbai
    f = e.features(tx(600, device_id="d2", lat=28.61, lon=77.20))   # Delhi 10 min later
    assert f["new_device"] == 1 and f["known_device_count"] == 1
    assert f["location_change"] == 1 and 1100 < f["distance_from_prev_km"] < 1200
    assert f["implied_speed_kmh"] > 5000                           # impossible travel
    g = e.features(tx(600, device_id="d1", lat=19.07, lon=72.87))
    assert g["new_device"] == 0 and haversine_km(0, 0, 0, 0) == 0


def test_unknown_group_rejected():
    with pytest.raises(ValueError):
        FeatureEngine(groups=("nope",))


def test_time_split_is_chronological_and_disjoint():
    df = pd.DataFrame({"ts": np.sort(np.random.default_rng(1).integers(0, 1000, 2000))})
    tr, va, te, cuts = time_split(df)
    assert (tr & va).sum() == 0 and (va & te).sum() == 0 and (tr | va | te).all()
    assert df.ts[tr].max() < df.ts[va].min() and df.ts[va].max() < df.ts[te].min()
    with pytest.raises(ValueError):
        time_split(df.sort_values("ts", ascending=False))


def test_preprocessor_fit_on_train_only_and_handles_unseen_category():
    df = pd.DataFrame({"a": [1.0, 2.0, None, 4.0], "txn_type": ["X", "Y", "X", "Y"]})
    p = Preprocessor(["a"]).fit(df)
    assert p.medians["a"] == 2.0
    out = p.transform(pd.DataFrame({"a": [None], "txn_type": ["NEW"]}))
    assert out.loc[0, "a"] == 2.0 and out.loc[0, ["txn_type=X", "txn_type=Y"]].sum() == 0


def test_loader_validation(tmp_path):
    with pytest.raises(FileNotFoundError):
        datasets.load_paysim(tmp_path / "missing.csv")
    (tmp_path / "bad.csv").write_text("a,b\n1,2\n")
    with pytest.raises(ValueError):
        datasets.load_paysim(tmp_path / "bad.csv")


def test_build_end_to_end_is_deterministic(tmp_path):
    src = tmp_path / "paysim_like.csv"
    make_paysim_like(3000, seed=3).to_csv(src, index=False)
    m1 = build(src, tmp_path / "o1", seed=42)
    m2 = build(src, tmp_path / "o2", seed=42)
    for name in ("train", "val", "test"):
        a = pd.read_csv(tmp_path / "o1" / f"features_{name}.csv.gz")
        b = pd.read_csv(tmp_path / "o2" / f"features_{name}.csv.gz")
        pd.testing.assert_frame_equal(a, b)
    assert m1["split"]["stats"] == m2["split"]["stats"] and m1["source_sha256"] == m2["source_sha256"]
    df = datasets.load_paysim(src)
    assert "isFlaggedFraud" not in df.columns and "newbalanceOrig" not in df.columns
    train = pd.read_csv(tmp_path / "o1" / "features_train.csv.gz")
    assert "is_fraud" in train.columns and train.ts.max() < m1["split"]["train_end_ts"]


# ---- balance feature group -------------------------------------------------------------------
def test_balance_features_legit_vs_drain():
    e = FeatureEngine(groups=("core", "balance"))
    ok = e.features(tx(0, amount=100.0, old_org=1000.0, new_org=900.0, old_dest=50.0, new_dest=150.0))
    assert ok["orig_balance_error"] == 0 and ok["dest_balance_error"] == 0
    assert ok["orig_emptied"] == 0 and ok["dest_balance_unchanged"] == 0
    bad = e.features(tx(1, amount=500.0, old_org=500.0, new_org=0.0, old_dest=0.0, new_dest=0.0))
    assert bad["orig_emptied"] == 1 and bad["dest_balance_unchanged"] == 1
    assert bad["dest_balance_error"] == 500.0 and bad["amount_to_orig_balance"] == pytest.approx(500 / 501)


def test_balance_features_missing_are_nan_and_default_group_unchanged():
    f = FeatureEngine(groups=("core", "balance")).features(tx(0))
    assert np.isnan(f["orig_balance_error"]) and np.isnan(f["dest_balance_unchanged"])
    assert "orig_emptied" not in FeatureEngine().features(tx(0))        # core-only output is unchanged


def test_build_with_balance_flag(tmp_path):
    raw = make_paysim_like(n=3000, seed=1)
    raw["oldbalanceOrg"] = 1000.0
    raw["newbalanceOrig"] = np.where(raw["isFraud"] == 1, 0.0, 1000.0 - raw["amount"])
    csv = tmp_path / "ps.csv"
    raw.to_csv(csv, index=False)
    meta = build(csv, tmp_path / "out", balance=True)
    assert meta["balance_features"] is True and "oldbalanceOrg" not in meta["dropped_columns"]
    tr = pd.read_csv(tmp_path / "out" / "features_train.csv.gz")
    assert "orig_balance_error" in tr.columns and "orig_emptied" in tr.columns
    meta0 = build(csv, tmp_path / "out0")
    assert meta0["balance_features"] is False
