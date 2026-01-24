"""Sleeper and trap card detection.

Detects cards that over/under-perform relative to their pick rate
and perceived value.
"""

import logging
import statistics
from typing import Optional

from src.models.card import Card, CardStats
from src.models.meta import ThresholdConfig
from src.scoring.card_scorer import wilson_score_lower_bound, z_score

logger = logging.getLogger(__name__)


class IrregularityDetector:
    """Detects undervalued (sleeper) and overvalued (trap) cards."""

    def __init__(
        self,
        sleeper_z_threshold: float = 1.0,
        trap_z_threshold: float = -1.0,
        min_games: int = 200,
    ):
        """
        Initialize detector.

        Args:
            sleeper_z_threshold: Z-score above which card is a sleeper
            trap_z_threshold: Z-score below which card is a trap
            min_games: Minimum games for analysis
        """
        self.sleeper_z = sleeper_z_threshold
        self.trap_z = trap_z_threshold
        self.min_games = min_games

    @classmethod
    def from_thresholds(cls, thresholds: ThresholdConfig) -> "IrregularityDetector":
        """Create detector from calibrated thresholds."""
        # Sanity check: ensure thresholds are reasonable
        # If calibration produces extreme values, use defaults
        sleeper_z = thresholds.sleeper_z
        trap_z = thresholds.trap_z

        # Relaxed sanity bounds to accept reasonable calibrated values
        if sleeper_z > 2.5 or sleeper_z < 0.3:
            logger.warning(
                f"Calibrated sleeper_z={sleeper_z:.2f} is extreme, using default 1.0"
            )
            sleeper_z = 1.0

        if trap_z < -2.5 or trap_z > -0.3:
            logger.warning(
                f"Calibrated trap_z={trap_z:.2f} is extreme, using default -1.0"
            )
            trap_z = -1.0

        return cls(
            sleeper_z_threshold=sleeper_z,
            trap_z_threshold=trap_z,
            min_games=thresholds.min_games,
        )

    def _calculate_expected_wr(self, card: CardStats) -> float:
        """
        Calculate expected win rate based on pick behavior.

        Cards that are picked highly and early are expected to be good.
        This establishes a baseline to compare actual performance against.

        Args:
            card: Card statistics

        Returns:
            Expected win rate based on pick metrics
        """
        # Base expectation is average (50%)
        base = 0.50

        # Higher pick rate suggests card is valued → expect higher WR
        pick_adjustment = card.pick_rate * 0.12

        # Lower ALSA (picked earlier) suggests card is valued → expect higher WR
        # ALSA of 7 is average, below is better, above is worse
        alsa_adjustment = (7 - card.alsa) * 0.015

        return base + pick_adjustment + alsa_adjustment

    def _calculate_deviation(self, card: CardStats) -> float:
        """
        Calculate deviation between actual and expected win rate.

        Positive deviation = overperforming (sleeper)
        Negative deviation = underperforming (trap)
        """
        expected = self._calculate_expected_wr(card)
        actual = wilson_score_lower_bound(card.gih_wins, card.gih_games)

        return actual - expected

    def detect_irregularity(
        self,
        card: CardStats,
        all_cards: list[CardStats],
    ) -> tuple[str, float]:
        """
        Detect if card is a sleeper, trap, or normal.

        Args:
            card: Card to analyze
            all_cards: All cards for Z-score calculation

        Returns:
            tuple[str, float]: (category, z_score)
            - category: "sleeper", "trap", or "normal"
            - z_score: deviation z-score
        """
        # Filter to cards with sufficient data
        valid_cards = [c for c in all_cards if c.gih_games >= self.min_games]

        if len(valid_cards) < 20:
            logger.warning("Insufficient cards for irregularity detection")
            return ("normal", 0.0)

        # Calculate deviations for all cards
        deviations = [self._calculate_deviation(c) for c in valid_cards]
        card_deviation = self._calculate_deviation(card)

        # Calculate Z-score of this card's deviation
        z = z_score(card_deviation, deviations)

        # Classify
        if z >= self.sleeper_z:
            return ("sleeper", z)
        elif z <= self.trap_z:
            return ("trap", z)
        else:
            return ("normal", z)

    def analyze_card(
        self,
        card: Card,
        all_cards: list[Card],
    ) -> Card:
        """
        Analyze a card for irregularity and update it.

        Args:
            card: Card to analyze
            all_cards: All cards for context

        Returns:
            Card with irregularity fields updated
        """
        stats_list = [c.stats for c in all_cards]

        category, z = self.detect_irregularity(card.stats, stats_list)

        card.irregularity_type = category
        card.irregularity_z = z

        return card

    def analyze_all_cards(
        self,
        cards: list[Card],
    ) -> tuple[list[Card], list[Card], list[Card]]:
        """
        Analyze all cards for irregularities.

        Args:
            cards: All scored cards

        Returns:
            tuple of (all_cards, sleepers, traps)
        """
        stats_list = [c.stats for c in cards]

        sleepers = []
        traps = []

        for card in cards:
            category, z = self.detect_irregularity(card.stats, stats_list)
            card.irregularity_type = category
            card.irregularity_z = z

            if category == "sleeper":
                sleepers.append(card)
            elif category == "trap":
                traps.append(card)

        # Sort by Z-score magnitude
        sleepers.sort(key=lambda c: c.irregularity_z, reverse=True)
        traps.sort(key=lambda c: c.irregularity_z)

        logger.info(
            f"Irregularity analysis: {len(sleepers)} sleepers, {len(traps)} traps"
        )

        return cards, sleepers, traps


def calculate_archetype_variance(
    card: CardStats,
    archetype_data: dict[str, list[dict]],
    min_games: int = 200,
) -> tuple[float, float, bool]:
    """
    Calculate how much a card's performance varies across archetypes.

    Args:
        card: Card to analyze
        archetype_data: Dict of archetype -> card ratings
        min_games: Minimum games in archetype for inclusion

    Returns:
        tuple[float, float, bool]: (variance, stability_score, is_synergy_dependent)
    """
    archetype_wrs = {}

    for colors, ratings in archetype_data.items():
        if len(colors) != 2:  # Only two-color archetypes
            continue

        # Find this card in archetype data
        for rating in ratings:
            if rating.get("name") == card.name:
                games = rating.get("ever_drawn_game_count", 0) or 0
                if games >= min_games:
                    wr = rating.get("ever_drawn_win_rate", 0.0) or 0.0
                    archetype_wrs[colors] = wr
                break

    if len(archetype_wrs) < 3:
        # Not enough data for variance calculation
        return 0.0, 100.0, False

    # Calculate variance
    variance = statistics.variance(archetype_wrs.values())

    # Calculate stability score (inverse of variance, scaled)
    # variance of 0 = stability 100
    # variance of 0.005 (~7%p spread) = stability 0
    stability = max(0, 100 - (variance / 0.00005))

    # Synergy-dependent if variance is high (>2%p spread)
    is_synergy_dependent = variance > 0.0004

    return variance, stability, is_synergy_dependent


def enrich_cards_with_variance(
    cards: list[Card],
    archetype_data: dict[str, list[dict]],
    min_games: int = 200,
) -> list[Card]:
    """
    Enrich all cards with archetype variance data.

    Args:
        cards: Scored cards to enrich
        archetype_data: Dict of archetype -> card ratings
        min_games: Minimum games for inclusion

    Returns:
        Cards with variance fields updated
    """
    for card in cards:
        variance, stability, synergy_dep = calculate_archetype_variance(
            card.stats, archetype_data, min_games
        )

        card.archetype_variance = variance
        card.stability_score = stability
        card.is_synergy_dependent = synergy_dep

        # Also store archetype WRs in stats
        for colors, ratings in archetype_data.items():
            if len(colors) != 2:
                continue
            for rating in ratings:
                if rating.get("name") == card.name:
                    games = rating.get("ever_drawn_game_count", 0) or 0
                    if games >= min_games:
                        wr = rating.get("ever_drawn_win_rate", 0.0) or 0.0
                        card.stats.archetype_wrs[colors] = wr
                        card.stats.archetype_games[colors] = games
                    break

    synergy_count = sum(1 for c in cards if c.is_synergy_dependent)
    logger.info(f"Variance analysis: {synergy_count} synergy-dependent cards")

    return cards
