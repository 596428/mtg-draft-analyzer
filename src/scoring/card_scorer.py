"""Card scoring with Bayesian adjustment and Z-Score normalization."""

import logging
import statistics
from math import sqrt
from typing import Optional

import yaml

from src.models.card import Card, CardStats
from src.models.meta import ThresholdConfig

logger = logging.getLogger(__name__)


def wilson_score_lower_bound(wins: int, games: int, z: float = 1.96) -> float:
    """
    Calculate Wilson Score Lower Bound for win rate.

    This provides a conservative estimate of win rate that accounts for
    sample size uncertainty. With small samples, it regresses toward 50%.

    Args:
        wins: Number of wins
        games: Total games played
        z: Z-score for confidence level (1.96 = 95% CI)

    Returns:
        Lower bound of confidence interval for win rate

    Examples:
        - 60 wins / 100 games → ~50.4%
        - 600 wins / 1000 games → ~56.9%
        - 6000 wins / 10000 games → ~59.0%
    """
    if games == 0:
        return 0.5

    p = wins / games
    denominator = 1 + z**2 / games
    centre = p + z**2 / (2 * games)
    adjustment = z * sqrt((p * (1 - p) + z**2 / (4 * games)) / games)

    return (centre - adjustment) / denominator


def z_score(value: float, values: list[float]) -> float:
    """
    Calculate Z-score (standard score).

    Args:
        value: Value to calculate Z-score for
        values: Population of values

    Returns:
        Z-score (standard deviations from mean)
    """
    if len(values) < 2:
        return 0.0

    mean = statistics.mean(values)
    std = statistics.stdev(values)

    if std == 0:
        return 0.0

    return (value - mean) / std


class CardScorer:
    """Calculates composite scores for MTG cards."""

    DEFAULT_WEIGHTS = {
        "gih_wr": 0.45,
        "iwd": 0.20,
        "alsa_inverse": 0.15,
        "oh_wr": 0.10,
        "gd_wr": 0.10,
    }

    GRADE_THRESHOLDS = {
        "A+": 90,
        "A": 80,
        "B+": 70,
        "B": 60,
        "C+": 50,
        "C": 40,
        "D": 30,
        "F": 0,
    }

    def __init__(
        self,
        weights: Optional[dict[str, float]] = None,
        bayesian_z: float = 1.96,
        min_games: int = 500,
        scale_center: int = 50,
        scale_multiplier: int = 15,
    ):
        """
        Initialize card scorer.

        Args:
            weights: Scoring weights (must sum to 1.0)
            bayesian_z: Z-score for Wilson confidence interval
            min_games: Minimum games for reliable stats
            scale_center: Center point for 0-100 scaling (Z=0 maps here)
            scale_multiplier: Multiplier for Z-score scaling
        """
        self.weights = weights or self.DEFAULT_WEIGHTS
        self.bayesian_z = bayesian_z
        self.min_games = min_games
        self.scale_center = scale_center
        self.scale_multiplier = scale_multiplier

        # Validate weights
        weight_sum = sum(self.weights.values())
        if abs(weight_sum - 1.0) > 0.001:
            logger.warning(f"Weights sum to {weight_sum}, not 1.0. Normalizing.")
            for key in self.weights:
                self.weights[key] /= weight_sum

    @classmethod
    def from_config(cls, config_path: str = "config/scoring.yaml") -> "CardScorer":
        """Create scorer from YAML config file."""
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        scoring_config = config.get("scoring", {})
        return cls(
            weights=scoring_config.get("weights"),
            bayesian_z=scoring_config.get("bayesian", {}).get("confidence_z", 1.96),
            min_games=scoring_config.get("bayesian", {}).get("min_sample_size", 500),
            scale_center=scoring_config.get("scaling", {}).get("center", 50),
            scale_multiplier=scoring_config.get("scaling", {}).get("multiplier", 15),
        )

    def calculate_bayesian_wr(self, card: CardStats) -> float:
        """Calculate Bayesian-adjusted win rate.

        Returns 0.5 for cards with no win rate data.
        """
        if card.gih_wr is None:
            return 0.5  # Neutral baseline for missing data
        return wilson_score_lower_bound(
            card.gih_wins, card.gih_games, self.bayesian_z
        )

    def calculate_composite_score(
        self,
        card: CardStats,
        all_cards: list[CardStats],
    ) -> float:
        """
        Calculate composite score (0-100) for a card.

        Args:
            card: Card to score
            all_cards: All cards for Z-score calculation

        Returns:
            Composite score (0-100)
            Returns 0.0 for cards with no win rate data.
        """
        # Skip cards with no win rate data
        if card.gih_wr is None:
            return 0.0

        # Filter cards with sufficient data AND valid win rates
        valid_cards = [
            c for c in all_cards
            if c.gih_games >= self.min_games and c.gih_wr is not None
        ]

        if len(valid_cards) < 10:
            logger.warning("Insufficient cards for reliable Z-score calculation")
            # Fall back to all cards with valid win rates
            valid_cards = [c for c in all_cards if c.gih_wr is not None]

        if len(valid_cards) < 2:
            return 50.0  # Neutral score if not enough data

        # Calculate Bayesian-adjusted win rates
        adj_wrs = [self.calculate_bayesian_wr(c) for c in valid_cards]
        card_adj_wr = self.calculate_bayesian_wr(card)

        # Calculate Z-scores for each metric
        z_scores = {}

        # GIH WR (Bayesian adjusted)
        z_scores["gih_wr"] = z_score(card_adj_wr, adj_wrs)

        # IWD (Improvement When Drawn) - filter out None values
        iwds = [c.iwd for c in valid_cards if c.iwd is not None]
        if iwds and card.iwd is not None:
            z_scores["iwd"] = z_score(card.iwd, iwds)
        else:
            z_scores["iwd"] = 0.0

        # ALSA Inverse (14 - ALSA, higher = picked earlier = better)
        alsa_inverses = [14 - c.alsa for c in valid_cards]
        z_scores["alsa_inverse"] = z_score(14 - card.alsa, alsa_inverses)

        # Opening Hand WR - filter out None values
        oh_wrs = [c.oh_wr for c in valid_cards if c.oh_games >= 100 and c.oh_wr is not None]
        if oh_wrs and card.oh_wr is not None:
            z_scores["oh_wr"] = z_score(card.oh_wr, oh_wrs)
        else:
            z_scores["oh_wr"] = 0.0

        # Games Drawn WR - filter out None values
        gd_wrs = [c.gd_wr for c in valid_cards if c.gd_games >= 100 and c.gd_wr is not None]
        if gd_wrs and card.gd_wr is not None:
            z_scores["gd_wr"] = z_score(card.gd_wr, gd_wrs)
        else:
            z_scores["gd_wr"] = 0.0

        # Calculate weighted sum
        raw_score = sum(
            self.weights.get(metric, 0) * z
            for metric, z in z_scores.items()
        )

        # Scale to 0-100
        # Z=0 → 50, Z=2 → 80, Z=-2 → 20
        scaled = self.scale_center + raw_score * self.scale_multiplier

        # Clamp to valid range
        return max(0, min(100, scaled))

    def assign_grade(self, score: float) -> str:
        """
        Assign letter grade based on score.

        Args:
            score: Composite score (0-100)

        Returns:
            Letter grade (A+, A, B+, B, C+, C, D, F)
        """
        for grade, threshold in self.GRADE_THRESHOLDS.items():
            if score >= threshold:
                return grade
        return "F"

    def score_card(
        self,
        card: CardStats,
        all_cards: list[CardStats],
    ) -> Card:
        """
        Score a card and return enriched Card object.

        Args:
            card: CardStats to score
            all_cards: All cards for context

        Returns:
            Card object with computed scores
        """
        # Handle cards with no win rate data
        if card.gih_wr is None:
            return Card(
                stats=card,
                composite_score=0.0,
                grade="N/A",
                adjusted_gih_wr=0.0,
                irregularity_type="no_data",
            )

        score = self.calculate_composite_score(card, all_cards)
        grade = self.assign_grade(score)
        adj_wr = self.calculate_bayesian_wr(card)

        return Card(
            stats=card,
            composite_score=score,
            grade=grade,
            adjusted_gih_wr=adj_wr,
        )

    def score_all_cards(
        self,
        cards: list[CardStats],
        thresholds: Optional[ThresholdConfig] = None,
    ) -> list[Card]:
        """
        Score all cards in a set.

        Args:
            cards: List of CardStats
            thresholds: Optional calibrated thresholds

        Returns:
            List of scored Card objects
        """
        scored_cards = []

        for card in cards:
            scored = self.score_card(card, cards)
            scored_cards.append(scored)

        # Sort by score descending
        scored_cards.sort(key=lambda c: c.composite_score, reverse=True)

        logger.info(f"Scored {len(scored_cards)} cards")

        return scored_cards
