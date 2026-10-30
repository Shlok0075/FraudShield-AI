"""
Unit tests for the decision engine + predict wrapper (PART 15 ML TESTING).
Run: pytest ml/src/test_ml.py -v
"""
import numpy as np
import pytest

from decision_engine import (
    DECISION_MAP,
    evaluate,
    probability_to_risk_score,
    risk_score_to_level,
    should_create_alert,
)


def test_probability_to_risk_score_bounds():
    assert probability_to_risk_score(0.0) == 0
    assert probability_to_risk_score(1.0) == 100
    assert probability_to_risk_score(0.874) == 87


def test_probability_to_risk_score_rejects_out_of_range():
    with pytest.raises(ValueError):
        probability_to_risk_score(1.5)
    with pytest.raises(ValueError):
        probability_to_risk_score(-0.1)


@pytest.mark.parametrize("score,expected", [
    (0, "LOW"), (29, "LOW"), (30, "MEDIUM"), (59, "MEDIUM"),
    (60, "HIGH"), (79, "HIGH"), (80, "CRITICAL"), (100, "CRITICAL"),
])
def test_risk_score_to_level_every_branch(score, expected):
    assert risk_score_to_level(score) == expected


def test_decision_map_covers_every_level():
    for level in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]:
        assert level in DECISION_MAP


@pytest.mark.parametrize("level,expected", [
    ("LOW", False), ("MEDIUM", True), ("HIGH", True), ("CRITICAL", True),
])
def test_should_create_alert(level, expected):
    assert should_create_alert(level) == expected


def test_evaluate_low_risk_allows():
    result = evaluate(0.05)
    assert result.risk_level == "LOW"
    assert result.decision == "Allow"
    assert result.create_alert is False
    assert result.alert_severity is None


def test_evaluate_critical_risk_alerts():
    result = evaluate(0.95)
    assert result.risk_level == "CRITICAL"
    assert result.decision == "Critical Alert"
    assert result.create_alert is True
    assert result.alert_severity == "CRITICAL"


def test_predict_end_to_end_smoke():
    """Loads the real trained model.joblib and confirms the full predict()
    pipeline runs and returns a well-formed result. Requires ml/models/
    artifacts to already exist (run `python ml/src/train.py` first)."""
    from predict import predict

    normal_row = {"Amount_scaled": 0.1, "Time_scaled": 0.0}
    fraud_like_row = {"V4": 3.0, "V11": 2.8, "V17": -2.5, "Amount_scaled": 3.5}

    normal_result = predict(normal_row)
    fraud_result = predict(fraud_like_row)

    for result in (normal_result, fraud_result):
        assert 0.0 <= result["probability"] <= 1.0
        assert 0 <= result["risk_score"] <= 100
        assert result["risk_level"] in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        assert isinstance(result["explanation"], list)
        assert len(result["explanation"]) > 0

    # The deliberately fraud-shaped row should score at least as risky.
    assert fraud_result["risk_score"] >= normal_result["risk_score"]
