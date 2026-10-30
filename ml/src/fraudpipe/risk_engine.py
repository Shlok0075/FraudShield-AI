"""
Hybrid fraud risk engine: supervised ML + anomaly + behavioral + deterministic rules -> 0-100 score,
risk level, ALLOW/REVIEW/BLOCK decision and human-readable reasons.

    FinalRisk = 100 * sum(w_i * s_i) / sum(w_i)      over the signals that are AVAILABLE for this transaction

Signals ml / anomaly / behavior / rules are each in [0, 1]. A missing signal (e.g. no anomaly model loaded, or a
feature that is NaN) is left out and the remaining weights are renormalised - never silently treated as 0.

Weights and thresholds live in RiskConfig (JSON-serialisable). They are NOT hand-picked: see tune.py, which
selects them on VALIDATION data and reports every candidate.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field

CONFIG_VERSION = "risk-v1"
SIGNALS = ("ml", "anomaly", "behavior", "rules")
LEVELS = {"LOW": (0, 29), "MEDIUM": (30, 59), "HIGH": (60, 79), "CRITICAL": (80, 100)}


@dataclass
class RuleConfig:
    """Thresholds/points for deterministic rules. `points` are added and capped at 1.0 to form the rule score."""
    max_speed_kmh: float = 900.0
    amount_ratio: float = 8.0            # amount / user's mean prior amount
    amount_zscore: float = 4.0
    min_history: int = 5                 # baseline rules need this many prior txns
    burst_1m: int = 5
    burst_1h: int = 15
    card_test_count_5m: int = 3
    card_test_max_ratio: float = 0.3     # small amounts relative to the user's average
    merchant_fraud_rate: float = 0.05
    unusual_hour_ratio: float = 3.0
    points: dict = field(default_factory=lambda: {
        "impossible_velocity": 0.9, "extreme_amount_deviation": 0.5, "new_device_and_location_change": 0.6,
        "card_testing": 0.6, "transaction_burst": 0.5, "suspicious_counterparty": 0.5,
        "unusual_hour_high_amount": 0.3})


@dataclass
class RiskConfig:
    weights: dict = field(default_factory=lambda: {"ml": 0.5, "anomaly": 0.15, "behavior": 0.2, "rules": 0.15})
    review_threshold: float = 40.0       # score >= -> REVIEW
    block_threshold: float = 80.0        # score >= -> BLOCK
    force_review_rules: tuple = ("impossible_velocity",)
    behavior_min_history: int = 5
    rules: RuleConfig = field(default_factory=RuleConfig)
    version: str = CONFIG_VERSION
    provenance: str = "default (UNTUNED) - run fraudpipe.tune to select weights on validation data"

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, s: str) -> "RiskConfig":
        d = json.loads(s)
        d["rules"] = RuleConfig(**d["rules"])
        d["force_review_rules"] = tuple(d.get("force_review_rules", ()))
        return cls(**d)

    def validate(self) -> None:
        if set(self.weights) - set(SIGNALS) or any(w < 0 for w in self.weights.values()):
            raise ValueError("weights must be >= 0 and keyed by " + ", ".join(SIGNALS))
        if sum(self.weights.values()) <= 0:
            raise ValueError("at least one weight must be positive")
        if not 0 <= self.review_threshold <= self.block_threshold <= 100:
            raise ValueError("need 0 <= review_threshold <= block_threshold <= 100")


def _ok(x) -> bool:
    return x is not None and not (isinstance(x, float) and math.isnan(x))


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


# --------------------------------------------------------------------------- rules
def evaluate_rules(f: dict, rc: RuleConfig) -> list[dict]:
    """Return triggered rules [{name, points, description}]. A rule on a missing (NaN) feature does not fire."""
    hit = []

    def add(name, desc):
        hit.append({"name": name, "points": rc.points[name], "description": desc})

    n = f.get("user_txn_count_prior", 0)
    if _ok(f.get("implied_speed_kmh")) and f["implied_speed_kmh"] > rc.max_speed_kmh:
        add("impossible_velocity", f"Implied travel speed {f['implied_speed_kmh']:.0f} km/h between consecutive transactions")
    if n >= rc.min_history and ((_ok(f.get("amount_vs_user_avg")) and f["amount_vs_user_avg"] >= rc.amount_ratio)
                                or (_ok(f.get("amount_zscore")) and f["amount_zscore"] >= rc.amount_zscore)):
        add("extreme_amount_deviation",
            f"Amount is {f['amount_vs_user_avg']:.1f}x the user's average (z-score {f['amount_zscore']:.1f})")
    if f.get("new_device") == 1 and f.get("location_change") == 1:
        add("new_device_and_location_change", "New device used from a different location than the previous transaction")
    if (f.get("txn_count_5m", 0) >= rc.card_test_count_5m and n >= 1
            and _ok(f.get("amount_vs_user_avg")) and f["amount_vs_user_avg"] <= rc.card_test_max_ratio):
        add("card_testing", f"{f['txn_count_5m']} small transactions within 5 minutes")
    if f.get("txn_count_1m", 0) >= rc.burst_1m or f.get("txn_count_1h", 0) >= rc.burst_1h:
        add("transaction_burst", f"Burst of activity: {f.get('txn_count_1m', 0)} in 1 min, {f.get('txn_count_1h', 0)} in 1 h")
    if f.get("counterparty_fraud_rate_prior", 0.0) >= rc.merchant_fraud_rate:
        add("suspicious_counterparty",
            f"Counterparty's confirmed-fraud rate is {f['counterparty_fraud_rate_prior']:.1%}")
    if f.get("unusual_hour") == 1 and _ok(f.get("amount_vs_user_avg")) and n >= 1 \
            and f["amount_vs_user_avg"] >= rc.unusual_hour_ratio:
        add("unusual_hour_high_amount", "High amount at an unusual hour")
    return hit


def rule_score(hit: list[dict]) -> float:
    return _clip01(sum(h["points"] for h in hit))


# --------------------------------------------------------------------------- behavior
def behavior_score(f: dict, min_history: int = 5) -> float:
    """Deterministic deviation-from-baseline score in [0,1].

    Baseline-relative parts (amount) are scaled by history confidence = min(1, prior_txns / min_history), so a
    brand-new account is not judged against a meaningless baseline. Missing parts are skipped.
    """
    conf = min(1.0, f.get("user_txn_count_prior", 0) / max(min_history, 1))
    parts = []   # (value in [0,1], weight)
    if _ok(f.get("amount_vs_user_avg")):
        parts.append((conf * _clip01(math.log(max(f["amount_vs_user_avg"], 1.0)) / math.log(10.0)), 0.30))
    if _ok(f.get("amount_zscore")):
        parts.append((conf * _clip01(f["amount_zscore"] / 5.0), 0.20))
    parts.append((_clip01(f.get("txn_count_5m", 0) / 5.0), 0.15))
    parts.append((float(f.get("unusual_hour", 0)), 0.05))
    if _ok(f.get("new_device")):
        parts.append((float(f["new_device"]) * (1.0 if f.get("known_device_count", 0) > 0 else 0.3), 0.15))
    if _ok(f.get("location_change")):
        parts.append((float(f["location_change"]), 0.15))
    tot = sum(w for _, w in parts)
    return _clip01(sum(v * w for v, w in parts) / tot) if tot else 0.0


# --------------------------------------------------------------------------- aggregation
def aggregate(signals: dict, weights: dict) -> tuple[float, dict]:
    """signals: name -> value in [0,1] or None. Returns (score 0-100, per-signal contribution in points)."""
    avail = {k: v for k, v in signals.items() if _ok(v) and weights.get(k, 0) > 0}
    tot = sum(weights[k] for k in avail)
    if tot <= 0:
        return 0.0, {}
    contrib = {k: 100.0 * weights[k] * _clip01(v) / tot for k, v in avail.items()}
    return sum(contrib.values()), contrib


def risk_level(score: float) -> str:
    s = int(round(score))
    for lvl, (lo, hi) in LEVELS.items():
        if lo <= s <= hi:
            return lvl
    return "CRITICAL"


def decide(score: float, cfg: RiskConfig, triggered: list[dict]) -> str:
    if score >= cfg.block_threshold:
        return "BLOCK"
    if score >= cfg.review_threshold or any(t["name"] in cfg.force_review_rules for t in triggered):
        return "REVIEW"
    return "ALLOW"


def reasons(f: dict, triggered: list[dict]) -> list[str]:
    out = []
    n = f.get("user_txn_count_prior", 0)
    if n >= 1 and _ok(f.get("amount_vs_user_avg")) and f["amount_vs_user_avg"] >= 3:
        out.append(f"Amount is {f['amount_vs_user_avg']:.1f}x the user's average of {n} prior transactions.")
    if f.get("unusual_hour") == 1:
        out.append(f"Transaction occurred at an unusual hour ({int(f['hour_of_day']):02d}:00 UTC).")
    if f.get("new_device") == 1 and f.get("known_device_count", 0) > 0:
        out.append("Device has not previously been associated with the account.")
    if f.get("location_change") == 1 and _ok(f.get("distance_from_prev_km")):
        out.append(f"Location is {f['distance_from_prev_km']:.0f} km from the previous transaction.")
    if f.get("txn_count_5m", 0) >= 3:
        out.append(f"{f['txn_count_5m']} transactions by this user in the last 5 minutes.")
    if f.get("is_first_txn") == 1:
        out.append("First observed transaction for this user (no behavioral baseline yet).")
    out += [t["description"] + "." for t in triggered if t["description"] + "." not in out]
    return out


def score_transaction(features: dict, ml_prob: float | None, anomaly: float | None = None,
                      cfg: RiskConfig | None = None) -> dict:
    cfg = cfg or RiskConfig()
    cfg.validate()
    hit = evaluate_rules(features, cfg.rules)
    sig = {"ml": ml_prob, "anomaly": anomaly, "behavior": behavior_score(features, cfg.behavior_min_history),
           "rules": rule_score(hit)}
    score, contrib = aggregate(sig, cfg.weights)
    return {
        "final_risk_score": round(score, 1), "risk_score": int(round(score)), "risk_level": risk_level(score),
        "decision": decide(score, cfg, hit),
        "ml_score": ml_prob, "anomaly_score": anomaly,
        "behavior_score": sig["behavior"], "rule_score": sig["rules"],
        "triggered_rules": hit, "reasons": reasons(features, hit),
        "signal_contributions": {k: round(v, 2) for k, v in contrib.items()},
        "weights_used": {k: cfg.weights[k] for k in contrib}, "config_version": cfg.version,
    }
