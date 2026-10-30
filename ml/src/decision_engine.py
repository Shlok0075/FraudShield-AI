"""
FraudShield AI - Risk Scoring & Decision Engine (PART 10.12 / 10.13)
=====================================================================
Pure, independently unit-testable functions that turn a raw fraud
probability into a risk_score / risk_level / decision. Thresholds are
NOT hardcoded magic numbers scattered through the codebase -- they live
here as configurable constants so they can be tuned without touching
the API layer.

ACADEMIC DISCLAIMER: this is a demonstration policy for a student
prototype, not a real banking authorization/compliance policy.
"""
from dataclasses import dataclass

# Configurable thresholds (PART 10.12) -- risk_score is 0-100
RISK_THRESHOLDS = {
    "LOW": (0, 29),
    "MEDIUM": (30, 59),
    "HIGH": (60, 79),
    "CRITICAL": (80, 100),
}

# Configurable decision mapping (PART 10.13)
DECISION_MAP = {
    "LOW": "Allow",
    "MEDIUM": "Monitor",
    "HIGH": "Flag",
    "CRITICAL": "Critical Alert",
}

# An alert row is only created once risk reaches MEDIUM or above.
ALERT_MIN_LEVEL = "MEDIUM"
_LEVEL_ORDER = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def probability_to_risk_score(probability: float) -> int:
    """risk_score = round(fraud_probability * 100), clamped to [0, 100]."""
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be between 0 and 1")
    return max(0, min(100, round(probability * 100)))


def risk_score_to_level(risk_score: int) -> str:
    for level, (low, high) in RISK_THRESHOLDS.items():
        if low <= risk_score <= high:
            return level
    raise ValueError(f"risk_score {risk_score} out of range")


def decide(risk_level: str) -> str:
    if risk_level not in DECISION_MAP:
        raise ValueError(f"Unknown risk level: {risk_level}")
    return DECISION_MAP[risk_level]


def should_create_alert(risk_level: str) -> bool:
    return _LEVEL_ORDER.index(risk_level) >= _LEVEL_ORDER.index(ALERT_MIN_LEVEL)


def alert_severity(risk_level: str) -> str:
    """Maps risk level directly to alert severity (documented 1:1 choice)."""
    return risk_level


@dataclass
class DecisionResult:
    probability: float
    risk_score: int
    risk_level: str
    decision: str
    create_alert: bool
    alert_severity: str | None


def evaluate(probability: float) -> DecisionResult:
    """Full pipeline: probability -> risk_score -> risk_level -> decision."""
    risk_score = probability_to_risk_score(probability)
    risk_level = risk_score_to_level(risk_score)
    decision = decide(risk_level)
    create_alert = should_create_alert(risk_level)
    severity = alert_severity(risk_level) if create_alert else None
    return DecisionResult(
        probability=probability,
        risk_score=risk_score,
        risk_level=risk_level,
        decision=decision,
        create_alert=create_alert,
        alert_severity=severity,
    )
