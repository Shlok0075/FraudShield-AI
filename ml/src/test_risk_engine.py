"""Tests for the hybrid risk engine. Run: cd ml/src && pytest test_risk_engine.py -v"""
import numpy as np
import pytest

from fraudpipe.features import FeatureEngine, Txn
from fraudpipe.risk_engine import (RiskConfig, RuleConfig, aggregate, behavior_score, decide, evaluate_rules,
                                   risk_level, rule_score, score_transaction)
from fraudpipe.tune import combine, tune, weight_grid

T0 = 1_704_067_200


def warm(n=8, amount=100.0, groups=("core", "device_geo"), **kw):
    e = FeatureEngine(groups=groups)
    for i in range(n):
        e.process(Txn(T0 + i * 7200, "u", "m", amount, "PAYMENT", "d1", 19.07, 72.87))
    return e


def test_aggregate_renormalises_missing_signals_instead_of_zeroing():
    w = {"ml": .5, "anomaly": .2, "behavior": .2, "rules": .1}
    full, _ = aggregate({"ml": 1, "anomaly": 1, "behavior": 1, "rules": 1}, w)
    part, contrib = aggregate({"ml": 1, "anomaly": None, "behavior": 1, "rules": 1}, w)
    assert full == pytest.approx(100) and part == pytest.approx(100) and "anomaly" not in contrib
    assert aggregate({}, w) == (0.0, {})


def test_aggregate_is_weighted_mean_in_points():
    s, c = aggregate({"ml": 1.0, "rules": 0.0}, {"ml": .75, "rules": .25})
    assert s == pytest.approx(75) and c["ml"] == pytest.approx(75)


def test_normal_transaction_allowed_no_rules():
    e = warm()
    f = e.features(Txn(T0 + 9 * 7200, "u", "m", 105.0, "PAYMENT", "d1", 19.07, 72.87))
    assert evaluate_rules(f, RuleConfig()) == []
    r = score_transaction(f, 0.01, 0.1)
    assert r["decision"] == "ALLOW" and r["risk_level"] == "LOW"


def test_account_takeover_pattern_fires_rules_and_reasons():
    e = warm()
    f = e.features(Txn(T0 + 7 * 7200 + 600, "u", "m", 1500.0, "PAYMENT", "d_new", 28.61, 77.20))
    names = {t["name"] for t in evaluate_rules(f, RuleConfig())}
    assert {"impossible_velocity", "extreme_amount_deviation", "new_device_and_location_change"} <= names
    r = score_transaction(f, 0.9, 0.8)
    assert r["decision"] in ("REVIEW", "BLOCK") and r["risk_score"] >= 60
    text = " ".join(r["reasons"])
    assert "15.0x" in text and "not previously been associated" in text and "km" in text
    assert set(r["signal_contributions"]) == {"ml", "anomaly", "behavior", "rules"}


def test_impossible_velocity_forces_review_even_if_score_low():
    cfg = RiskConfig()
    hit = [{"name": "impossible_velocity", "points": .9, "description": "x"}]
    assert decide(5.0, cfg, hit) == "REVIEW" and decide(5.0, cfg, []) == "ALLOW"
    assert decide(80.0, cfg, []) == "BLOCK"


def test_card_testing_and_burst_rules():
    e = warm(n=6)
    for i in range(4):
        e.process(Txn(T0 + 6 * 7200 + i * 30, "u", "m", 5.0, "PAYMENT", "d1", 19.07, 72.87))
    f = e.features(Txn(T0 + 6 * 7200 + 150, "u", "m", 5.0, "PAYMENT", "d1", 19.07, 72.87))
    assert "card_testing" in {t["name"] for t in evaluate_rules(f, RuleConfig())}


def test_rules_ignore_nan_features_and_cold_start():
    f = FeatureEngine(groups=("core", "device_geo")).features(Txn(T0, "new", "m", 9999.0, "X", None, None, None))
    assert evaluate_rules(f, RuleConfig()) == []               # no baseline -> no baseline rules
    assert behavior_score(f) < 0.3                             # cold start is not judged against a fake baseline


def test_rule_score_capped_and_level_boundaries():
    assert rule_score([{"points": .8}, {"points": .8}]) == 1.0
    assert [risk_level(x) for x in (0, 29, 30, 59, 60, 79, 80, 100)] == \
        ["LOW", "LOW", "MEDIUM", "MEDIUM", "HIGH", "HIGH", "CRITICAL", "CRITICAL"]


def test_config_validation_and_json_roundtrip():
    c = RiskConfig()
    assert RiskConfig.from_json(c.to_json()) == c
    c.weights = {"ml": -1}
    with pytest.raises(ValueError):
        c.validate()
    c = RiskConfig(review_threshold=90, block_threshold=50)
    with pytest.raises(ValueError):
        c.validate()


def test_weight_grid_size_and_sums():
    g = list(weight_grid(("ml", "anomaly", "behavior", "rules")))
    assert len(g) == 286 and all(abs(sum(w.values()) - 1) < 1e-9 for w in g)


def test_tuning_prefers_informative_signal_and_enforces_threshold_order():
    rng = np.random.default_rng(0)
    y = (rng.random(6000) < .05).astype(int)
    sig = {"ml": np.clip(y * .6 + rng.random(6000) * .5, 0, 1), "anomaly": rng.random(6000),
           "behavior": rng.random(6000), "rules": np.zeros(6000)}
    cfg, table = tune(sig, y)
    assert cfg.weights["ml"] >= max(cfg.weights["anomaly"], cfg.weights["behavior"])
    assert cfg.review_threshold <= cfg.block_threshold and "tuned on validation" in cfg.provenance
    assert table.iloc[0].val_pr_auc >= table.val_pr_auc.max() - 1e-12 and len(table) == 286
    assert combine(sig, cfg.weights).shape == (6000,)
