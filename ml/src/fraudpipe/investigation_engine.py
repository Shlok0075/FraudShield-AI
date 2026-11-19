"""
FraudShield AI — Automated Investigation Engine.

Investigates flagged transactions automatically:
  1. Enriches context (device history, location, merchant reputation, user baseline)
  2. Runs automated checks (impossible travel, device sharing, velocity bursts, fraud ring links, amount deviation)
  3. Computes investigation confidence (0-100)
  4. Makes auto-decision: clear fraud → Auto-BLOCK; clear legitimate → Auto-ALLOW; ambiguous → REVIEW
  5. Generates a human-readable investigation report
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class InvestigationConfig:
    """Thresholds for auto-decision."""
    auto_block_confidence: int = 85    # weighted multi-signal confidence >= this -> auto-block
    # Decision guards (all signals are 0..1).
    auto_block_ml: float = 0.90        # model this sure + one corroborating signal -> auto-block
    corroborate_signal: float = 0.50   # another signal (graph/anomaly/rules/behaviour) at/above this corroborates
    strong_check_confidence: int = 60  # a passed automated check this strong also corroborates
    auto_clear_max_signal: float = 0.20  # EVERY signal must be below this for an auto-clear
    # Anything in between goes to a human analyst.
    # NOTE: a weighted AVERAGE alone is not safe for auto-clearing. The model's own score is only
    # 15% of it, so a transaction the model rated 0.99 fraud with nothing else firing averaged 15
    # and was auto-CLEARED. Clearing now needs every signal low, and a flagged transaction is
    # never cleared.

    # Evidence weights (must sum to 100)
    graph_risk_weight: int = 25
    anomaly_weight: int = 20
    rule_weight: int = 20
    behavior_weight: int = 20
    ml_prob_weight: int = 15


@dataclass
class CheckResult:
    name: str
    passed: bool          # True = evidence of fraud
    confidence: int       # 0-100
    description: str


@dataclass
class InvestigationResult:
    confidence: int               # 0-100 overall investigation confidence
    decision: str                 # "AUTO_BLOCK" / "AUTO_CLEAR" / "REVIEW"
    risk_level: str               # "LOW" / "MEDIUM" / "HIGH" / "CRITICAL"
    checks: list[CheckResult]
    summary: str                  # Human-readable one-line summary
    details: str                  # Detailed investigation report
    evidence: dict[str, Any]      # Raw evidence for dashboard display


class InvestigationEngine:
    """Automated fraud investigation engine."""

    def __init__(self, config: InvestigationConfig | None = None):
        self.cfg = config or InvestigationConfig()

    # ------------------------------------------------------------------ main entry
    def investigate(
        self,
        *,
        ml_prob: float | None,
        anomaly_score: float | None,
        behavior_score: float | None,
        rule_score: float | None,
        graph_score: float | None,
        triggered_rules: list[dict],
        features: dict,
        graph_features: dict | None = None,
    ) -> InvestigationResult:
        """Run the full investigation pipeline and return a result."""
        graph_features = graph_features or {}

        # 1. Run automated checks
        checks: list[CheckResult] = []

        # Graph-based fraud ring check
        g = graph_score if graph_score is not None else 0.0
        checks.append(CheckResult(
            name="fraud_ring_exposure",
            passed=g >= 0.5,
            confidence=int(g * 100),
            description=self._graph_description(g, graph_features),
        ))

        # Impossible travel / velocity check
        velocity = self._velocity_check(features)
        checks.append(velocity)

        # Device sharing check
        device_sharing = self._device_sharing_check(graph_features)
        checks.append(device_sharing)

        # Amount deviation check
        amount_dev = self._amount_deviation_check(features)
        checks.append(amount_dev)

        # Card testing / velocity burst check
        burst = self._burst_check(features)
        checks.append(burst)

        # Suspicious counterparty check
        counterparty = self._counterparty_check(features)
        checks.append(counterparty)

        # Unusual hour + high amount check
        unusual_hour = self._unusual_hour_check(features)
        checks.append(unusual_hour)

        # 2. Compute weighted investigation confidence
        evidence_signals = [
            ("graph", g, self.cfg.graph_risk_weight),
            ("anomaly", anomaly_score if anomaly_score is not None else 0.0, self.cfg.anomaly_weight),
            ("rules", rule_score if rule_score is not None else 0.0, self.cfg.rule_weight),
            ("behavior", behavior_score if behavior_score is not None else 0.0, self.cfg.behavior_weight),
            ("ml", ml_prob if ml_prob is not None else 0.0, self.cfg.ml_prob_weight),
        ]

        total_weight = sum(w for _, _, w in evidence_signals if w > 0)
        weighted_sum = sum(s * w for _, s, w in evidence_signals if w > 0)
        weighted = int(round(100.0 * weighted_sum / total_weight)) if total_weight > 0 else 0
        weighted = max(0, min(100, weighted))

        # Confidence is the stronger of the blended average and the single strongest signal, so one
        # very confident detector is not averaged away by four quiet ones.
        present = [s for _, s, _ in evidence_signals]
        peak = max(present) if present else 0.0
        confidence = max(weighted, int(round(100 * peak)))
        confidence = max(0, min(100, confidence))

        # 3. Auto-decision. Only AUTO_CLEAR and AUTO_BLOCK act without a human; both need
        # agreement, and a missing prediction can never auto-clear.
        failed = [c for c in checks if c.passed]
        corroborating = sum(1 for _, s, _ in evidence_signals
                            if s >= self.cfg.corroborate_signal) - (1 if (ml_prob or 0) >= self.cfg.corroborate_signal else 0)
        corroborating += sum(1 for c in failed if c.confidence >= self.cfg.strong_check_confidence)
        if ml_prob is not None and ml_prob >= self.cfg.auto_block_ml and corroborating >= 1:
            decision = "AUTO_BLOCK"
        elif weighted >= self.cfg.auto_block_confidence:
            decision = "AUTO_BLOCK"
        elif (ml_prob is not None and peak < self.cfg.auto_clear_max_signal
              and not triggered_rules and not failed):
            decision = "AUTO_CLEAR"
        else:
            decision = "REVIEW"

        # 4. Risk level band
        if confidence >= 80:
            risk_level = "CRITICAL"
        elif confidence >= 60:
            risk_level = "HIGH"
        elif confidence >= 40:
            risk_level = "MEDIUM"
        else:
            risk_level = "LOW"

        # 5. Generate report
        summary, details = self._build_report(confidence, decision, checks, features, evidence_signals)

        # 6. Evidence bundle for dashboard
        evidence = {
            "confidence": confidence,
            "ml_probability": ml_prob,
            "anomaly_score": anomaly_score,
            "behavior_score": behavior_score,
            "rule_score": rule_score,
            "graph_score": g,
            "triggered_rules": [r["name"] for r in triggered_rules],
            "graph_signals": {
                k: v for k, v in graph_features.items() if k.startswith("graph_")
            },
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "confidence": c.confidence,
                    "description": c.description,
                } for c in checks
            ],
            "investigated_at": datetime.now(timezone.utc).isoformat(),
        }

        return InvestigationResult(
            confidence=confidence,
            decision=decision,
            risk_level=risk_level,
            checks=checks,
            summary=summary,
            details=details,
            evidence=evidence,
        )

    # ------------------------------------------------------------------ individual checks
    def _graph_description(self, g: float, gf: dict) -> str:
        parts = []
        if g >= 0.7:
            parts.append("high fraud-ring exposure")
        elif g >= 0.4:
            parts.append("moderate fraud-ring exposure")
        if gf.get("graph_shared_fraud_device", 0) >= 0.5:
            parts.append("device shared with known fraud account")
        if gf.get("graph_device_farm", 0) >= 0.5:
            parts.append("device used by multiple recent users")
        if gf.get("graph_merchant_farm", 0) >= 0.5:
            parts.append("merchant used by multiple recent devices")
        if gf.get("graph_merchant_fraud_concentration", 0) >= 0.5:
            parts.append("merchant has recent fraud users")
        return "; ".join(parts) if parts else "low graph risk"

    def _velocity_check(self, features: dict) -> CheckResult:
        speed = features.get("implied_speed_kmh")
        txn_1m = features.get("txn_count_1m", 0)
        txn_1h = features.get("txn_count_1h", 0)
        passed = False
        conf = 0
        desc_parts = []
        if speed is not None and speed > 900:
            passed = True
            conf = max(conf, 90)
            desc_parts.append(f"impossible travel: {speed:.0f} km/h between consecutive transactions")
        if txn_1m >= 5:
            passed = True
            conf = max(conf, 70)
            desc_parts.append(f"velocity burst: {txn_1m} transactions in 1 minute")
        if txn_1h >= 15:
            passed = True
            conf = max(conf, 60)
            desc_parts.append(f"high hourly velocity: {txn_1h} transactions in 1 hour")
        return CheckResult(
            name="impossible_travel_velocity",
            passed=passed,
            confidence=conf,
            description="; ".join(desc_parts) if desc_parts else "normal travel velocity",
        )

    def _device_sharing_check(self, gf: dict) -> CheckResult:
        shared = gf.get("graph_shared_fraud_device", 0)
        device_farm = gf.get("graph_device_farm", 0)
        passed = shared >= 0.5 or device_farm >= 0.5
        conf = int(max(shared, device_farm) * 100)
        desc = []
        if shared >= 0.5:
            desc.append("device previously used by known fraud account")
        if device_farm >= 0.5:
            desc.append("device shared across multiple recent users (device farm pattern)")
        return CheckResult(
            name="device_sharing",
            passed=passed,
            confidence=conf,
            description="; ".join(desc) if desc else "device not shared with fraud accounts",
        )

    def _amount_deviation_check(self, features: dict) -> CheckResult:
        ratio = features.get("amount_vs_user_avg")
        zscore = features.get("amount_zscore")
        passed = False
        conf = 0
        desc = []
        if ratio is not None and ratio >= 8:
            passed = True
            conf = max(conf, 80)
            desc.append(f"amount is {ratio:.1f}x user's average")
        if zscore is not None and zscore >= 4:
            passed = True
            conf = max(conf, 75)
            desc.append(f"amount z-score {zscore:.1f}")
        return CheckResult(
            name="extreme_amount_deviation",
            passed=passed,
            confidence=conf,
            description="; ".join(desc) if desc else "amount within normal range",
        )

    def _burst_check(self, features: dict) -> CheckResult:
        txn_5m = features.get("txn_count_5m", 0)
        avg_ratio = features.get("amount_vs_user_avg", 1.0)
        passed = txn_5m >= 3 and (avg_ratio is None or avg_ratio <= 0.3)
        conf = int(min(100, txn_5m * 20)) if passed else 0
        desc = []
        if passed:
            desc.append(f"{txn_5m} small-value transactions in 5 minutes (card testing pattern)")
        return CheckResult(
            name="card_testing_burst",
            passed=passed,
            confidence=conf,
            description="; ".join(desc) if desc else "no card testing pattern detected",
        )

    def _counterparty_check(self, features: dict) -> CheckResult:
        rate = features.get("counterparty_fraud_rate_prior", 0.0)
        passed = rate >= 0.05
        conf = int(min(100, rate * 1000)) if passed else 0
        desc = []
        if passed:
            desc.append(f"counterparty fraud rate is {rate:.1%}")
        return CheckResult(
            name="suspicious_counterparty",
            passed=passed,
            confidence=conf,
            description="; ".join(desc) if desc else "counterparty has no known fraud history",
        )

    def _unusual_hour_check(self, features: dict) -> CheckResult:
        unusual = features.get("unusual_hour", 0)
        ratio = features.get("amount_vs_user_avg", 0) or 0
        passed = unusual == 1 and ratio >= 3
        conf = 60 if passed else 0
        desc = []
        if passed:
            desc.append(f"high amount ({ratio:.1f}x avg) at unusual hour")
        return CheckResult(
            name="unusual_hour_high_amount",
            passed=passed,
            confidence=conf,
            description="; ".join(desc) if desc else "normal transaction timing",
        )

    # ------------------------------------------------------------------ report building
    def _build_report(self, confidence, decision, checks, features, evidence_signals) -> tuple[str, str]:
        fraud_checks = [c for c in checks if c.passed]
        check_names = ", ".join(c.name for c in fraud_checks) if fraud_checks else "none"

        # Summary (one line)
        decision_label = {
            "AUTO_BLOCK": "auto-blocked",
            "AUTO_CLEAR": "auto-cleared",
            "REVIEW": "flagged for review",
        }[decision]
        summary = (
            f"Transaction {decision_label} with {confidence}% investigation confidence. "
            f"Evidence: {check_names}."
        )

        # Detailed report
        lines = [
            "FRAUDSHIELD AI — AUTOMATED INVESTIGATION REPORT",
            "=" * 50,
            f"Investigation Confidence: {confidence}%",
            f"Auto-Decision: {decision}",
            f"Risk Level: {self._risk_label(confidence)}",
            f"Investigated At: {datetime.now(timezone.utc).isoformat()}",
            "",
            "EVIDENCE SIGNALS:",
            "-" * 30,
        ]
        signal_labels = {
            "graph": "Graph Fraud-Ring Exposure",
            "anomaly": "Anomaly Detection (Isolation Forest)",
            "rules": "Deterministic Fraud Rules",
            "behavior": "Behavioral Deviation",
            "ml": "Supervised ML (XGBoost)",
        }
        for name, value, weight in evidence_signals:
            if weight <= 0:
                continue
            lines.append(f"  • {signal_labels.get(name, name)}: {value:.0%} (weight {weight}%)")

        lines.append("")
        lines.append("AUTOMATED CHECKS:")
        lines.append("-" * 30)
        if fraud_checks:
            for c in fraud_checks:
                lines.append(f"  [FRAUD] {c.name}: {c.description} (confidence {c.confidence}%)")
        else:
            lines.append("  No fraud indicators detected.")
        lines.append("")
        lines.append("REASONING:")
        lines.append("-" * 30)
        if decision == "AUTO_BLOCK":
            lines.append("  High-confidence fraud indicators detected across multiple signals.")
            lines.append("  Transaction automatically blocked. The case stays open: confirming fraud is an analyst decision.")
        elif decision == "AUTO_CLEAR":
            lines.append("  Every signal is low and no rule or check fired.")
            lines.append("  Transaction automatically cleared and case closed as legitimate.")
        else:
            lines.append("  Mixed signals — insufficient confidence for automatic decision.")
            lines.append("  Case assigned to human analyst for manual review.")
        lines.append("")
        lines.append("RECOMMENDED ACTION:")
        if decision == "AUTO_BLOCK":
            lines.append("  Keep the transaction blocked and have an analyst confirm or overturn it.")
        elif decision == "AUTO_CLEAR":
            lines.append("  Allow transaction, close the alert as a false positive.")
        else:
            lines.append("  Assign case to analyst for manual investigation.")

        return summary, "\n".join(lines)

    @staticmethod
    def _risk_label(confidence: int) -> str:
        if confidence >= 80:
            return "CRITICAL"
        if confidence >= 60:
            return "HIGH"
        if confidence >= 40:
            return "MEDIUM"
        return "LOW"


_investigation_engine: InvestigationEngine | None = None


def get_investigation_engine() -> InvestigationEngine:
    global _investigation_engine
    if _investigation_engine is None:
        _investigation_engine = InvestigationEngine()
    return _investigation_engine
