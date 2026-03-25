"""Confidence scoring and decision logic.

Aggregates signals from all pipeline stages into a final confidence score
and recommended action.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Action(Enum):
    AUTO_DEPLOY = "auto_deploy"
    HUMAN_REVIEW = "human_review"
    FLAG_FOR_INSPECTION = "flag_for_inspection"
    NO_MATCH = "no_match"


# Threshold boundaries for actions
THRESHOLDS = {
    Action.AUTO_DEPLOY: 0.90,
    Action.HUMAN_REVIEW: 0.70,
    Action.FLAG_FOR_INSPECTION: 0.50,
}


@dataclass
class StageSignal:
    """A confidence signal from one pipeline stage."""
    stage: str
    confidence: float
    weight: float = 1.0
    details: dict = field(default_factory=dict)


@dataclass
class ConfidenceResult:
    """Final confidence assessment from the pipeline."""
    score: float
    action: Action
    matched_platform: str | None
    signals: list[StageSignal]
    is_novel: bool = False

    @property
    def action_label(self) -> str:
        labels = {
            Action.AUTO_DEPLOY: "Auto-deploy (>= 0.90)",
            Action.HUMAN_REVIEW: "Human review (0.70 - 0.89)",
            Action.FLAG_FOR_INSPECTION: "Flag for inspection (0.50 - 0.69)",
            Action.NO_MATCH: "No match (< 0.50) — new scraper required",
        }
        return labels[self.action]


# Stage weights for the weighted average
STAGE_WEIGHTS = {
    "url_pattern": 3.0,
    "structural_similarity": 3.0,
}


def compute_confidence(signals: list[StageSignal]) -> ConfidenceResult:
    """Combine signals from multiple pipeline stages into a final score.

    Uses weighted average of all available signals. Each stage has a
    default weight that can be overridden in the StageSignal.
    """
    if not signals:
        return ConfidenceResult(
            score=0.0,
            action=Action.NO_MATCH,
            matched_platform=None,
            signals=[],
            is_novel=True,
        )

    total_weight = 0.0
    weighted_sum = 0.0

    for sig in signals:
        w = sig.weight if sig.weight != 1.0 else STAGE_WEIGHTS.get(sig.stage, 1.0)
        weighted_sum += sig.confidence * w
        total_weight += w

    score = weighted_sum / total_weight if total_weight > 0 else 0.0

    # Determine action
    if score >= THRESHOLDS[Action.AUTO_DEPLOY]:
        action = Action.AUTO_DEPLOY
    elif score >= THRESHOLDS[Action.HUMAN_REVIEW]:
        action = Action.HUMAN_REVIEW
    elif score >= THRESHOLDS[Action.FLAG_FOR_INSPECTION]:
        action = Action.FLAG_FOR_INSPECTION
    else:
        action = Action.NO_MATCH

    # Extract matched platform from signals
    matched_platform = None
    for sig in signals:
        if sig.details.get("platform"):
            matched_platform = sig.details["platform"]

    return ConfidenceResult(
        score=score,
        action=action,
        matched_platform=matched_platform,
        signals=signals,
        is_novel=(action == Action.NO_MATCH),
    )
