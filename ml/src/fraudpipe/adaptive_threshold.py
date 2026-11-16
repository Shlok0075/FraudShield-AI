"""
FraudShield AI — Context-aware adaptive thresholds.

Your current risk engine uses static thresholds (review=40, block=80). This module
replaces them with dynamic thresholds that adapt to transaction context:

  * amount tier        — higher amounts get lower thresholds (more scrutiny)
  * user history       — new users get stricter thresholds than established ones
  * merchant risk      — high-risk merchants need tighter controls
  * time context       — unusual hours / weekend nights raise scrutiny

The base thresholds come from RiskConfig (tuned on validation data), then each
context factor applies a multiplicative adjustment.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class AdaptiveThresholdConfig:
    """Configuration for context-aware threshold adjustments."""

    base_review_threshold: float = 40.0
    base_block_threshold: float = 80.0

    # Amount-tier adjustments (multiplier applied to base thresholds)
    # Lower multiplier = stricter (lower threshold → easier to flag)
    amount_tiers: list[dict[str, Any]] = field(default_factory=lambda: [
        {"max_amount": 1000.0,   "multiplier": 1.20},  # small amounts — more lenient
        {"max_amount": 5000.0,   "multiplier": 1.00},  # normal — baseline
        {"max_amount": 50000.0,  "multiplier": 0.85},  # high amount — stricter
        {"max_amount": float("inf"), "multiplier": 0.70},  # very high — strictest
    ])

    # New user adjustment (multiplier)
    new_user_max_prior_txns: int = 3
    new_user_multiplier: float = 0.85

    # Merchant fraud-rate adjustment
    high_risk_merchant_rate: float = 0.05
    high_risk_merchant_multiplier: float = 0.80

    # Unusual hour adjustment
    unusual_hour_multiplier: float = 0.90

    # Weekend adjustment (Sat=5, Sun=6)
    weekend_multiplier: float = 0.95

    # Floor / ceiling so thresholds never degenerate
    min_review_threshold: float = 15.0
    max_review_threshold: float = 85.0
    min_block_threshold: float = 50.0
    max_block_threshold: float = 95.0


def _tier_multiplier(amount: float, tiers: list[dict[str, Any]]) -> float:
    for tier in tiers:
        if amount <= tier["max_amount"]:
            return float(tier["multiplier"])
    return float(tiers[-1]["multiplier"])


class AdaptiveThresholdEngine:
    """Computes dynamic review/block thresholds for a given transaction context."""

    def __init__(self, config: AdaptiveThresholdConfig | None = None):
        self.cfg = config or AdaptiveThresholdConfig()

    def compute(self,
                *,
                amount: float,
                user_prior_txn_count: int,
                merchant_fraud_rate: float = 0.0,
                hour_of_day: int | None = None,
                is_weekend: bool = False,
                base_review: float | None = None,
                base_block: float | None = None,
                ) -> dict[str, float]:
        """Return {'review': float, 'block': float} dynamic thresholds."""

        review = base_review if base_review is not None else self.cfg.base_review_threshold
        block = base_block if base_block is not None else self.cfg.base_block_threshold

        # 1. Amount tier adjustment
        mult = _tier_multiplier(amount, self.cfg.amount_tiers)
        review *= mult
        block *= mult

        # 2. New user adjustment
        if user_prior_txn_count <= self.cfg.new_user_max_prior_txns:
            review *= self.cfg.new_user_multiplier
            block *= self.cfg.new_user_multiplier

        # 3. High-risk merchant adjustment
        if merchant_fraud_rate >= self.cfg.high_risk_merchant_rate:
            review *= self.cfg.high_risk_merchant_multiplier
            block *= self.cfg.high_risk_merchant_multiplier

        # 4. Unusual hour adjustment (22:00–05:00 UTC)
        if hour_of_day is not None and (hour_of_day >= 22 or hour_of_day <= 5):
            review *= self.cfg.unusual_hour_multiplier
            block *= self.cfg.unusual_hour_multiplier

        # 5. Weekend adjustment
        if is_weekend:
            review *= self.cfg.weekend_multiplier
            block *= self.cfg.weekend_multiplier

        # Clamp to safe ranges
        review = max(self.cfg.min_review_threshold,
                     min(self.cfg.max_review_threshold, review))
        block = max(self.cfg.min_block_threshold,
                    min(self.cfg.max_block_threshold, block))

        # Ensure block > review
        if block <= review:
            block = review + 5.0

        return {"review": round(review, 2), "block": round(block, 2)}


_adaptive_engine: AdaptiveThresholdEngine | None = None


def get_adaptive_engine() -> AdaptiveThresholdEngine:
    global _adaptive_engine
    if _adaptive_engine is None:
        _adaptive_engine = AdaptiveThresholdEngine()
    return _adaptive_engine
