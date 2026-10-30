"""Unit tests for risk scoring / decision engine, imported from ml/src via
sys.path (PART 15 UNIT TESTING). Every branch of the decision table is
exercised, per Week 13 Day 1's target."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ml" / "src"))
from decision_engine import evaluate, probability_to_risk_score, risk_score_to_level  # noqa: E402


@pytest.mark.parametrize("probability,expected_level,expected_decision", [
    (0.05, "LOW", "Allow"),
    (0.35, "MEDIUM", "Monitor"),
    (0.65, "HIGH", "Flag"),
    (0.90, "CRITICAL", "Critical Alert"),
])
def test_every_decision_branch(probability, expected_level, expected_decision):
    result = evaluate(probability)
    assert result.risk_level == expected_level
    assert result.decision == expected_decision


def test_alert_only_created_at_medium_and_above():
    assert evaluate(0.10).create_alert is False
    assert evaluate(0.31).create_alert is True


def test_risk_score_matches_formula():
    assert probability_to_risk_score(0.874) == 87
    assert probability_to_risk_score(0.5) == 50
    assert risk_score_to_level(50) == "MEDIUM"
