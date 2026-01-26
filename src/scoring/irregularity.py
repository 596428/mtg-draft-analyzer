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
        Detect if card is a sleeper, trap, normal, or no_data.

        Args:
            card: Card to analyze
            all_cards: All cards for Z-score calculation

        Returns:
            tuple[str, float]: (category, z_score)
            - category: "sleeper", "trap", "normal", or "no_data"
            - z_score: deviation z-score
        """
        # Skip cards with no win rate data
        if card.gih_wr is None:
            return ("no_data", 0.0)

        # Filter to cards with sufficient data AND valid win rates
        valid_cards = [
            c for c in all_cards
            if c.gih_games >= self.min_games and c.gih_wr is not None
        ]

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
    ) -> tuple[list[Card], list[Card], list[Card], list[Card]]:
        """
        Analyze all cards for irregularities.

        Args:
            cards: All scored cards

        Returns:
            tuple of (all_cards, sleepers, traps, no_data_cards)
        """
        stats_list = [c.stats for c in cards]

        sleepers = []
        traps = []
        no_data_cards = []

        for card in cards:
            # Skip cards already marked as no_data (from scorer)
            if card.irregularity_type == "no_data":
                no_data_cards.append(card)
                continue

            category, z = self.detect_irregularity(card.stats, stats_list)
            card.irregularity_type = category
            card.irregularity_z = z

            if category == "sleeper":
                sleepers.append(card)
            elif category == "trap":
                traps.append(card)
            elif category == "no_data":
                no_data_cards.append(card)

        # Sort by Z-score magnitude
        sleepers.sort(key=lambda c: c.irregularity_z, reverse=True)
        traps.sort(key=lambda c: c.irregularity_z)

        logger.info(
            f"Irregularity analysis: {len(sleepers)} sleepers, {len(traps)} traps, "
            f"{len(no_data_cards)} no_data"
        )

        return cards, sleepers, traps, no_data_cards


def calculate_viability(
    card: CardStats,
    archetype_data: dict[str, list[dict]],
    min_games: int = 50,
) -> tuple[int, Optional[str], float, Optional[float]]:
    """
    Calculate card viability across archetypes.

    Viability measures how flexibly a card can be used across different archetypes,
    focusing on practical utility rather than statistical variance.

    Args:
        card: Card to analyze
        archetype_data: Dict of archetype -> card ratings
        min_games: Minimum games for archetype inclusion

    Returns:
        tuple[int, Optional[str], float, Optional[float]]:
            (viable_archetypes, best_archetype, off_archetype_penalty, natural_premium)
        - viable_archetypes: Count of archetypes within 5% of best WR
        - best_archetype: Archetype with highest WR
        - off_archetype_penalty: Average WR drop in non-viable archetypes
        - natural_premium: Performance in card's natural colors vs others
    """
    # Collect archetype win rates (use ever_drawn_win_rate for consistency with gih_wr)
    archetype_wrs: dict[str, float] = {}

    for colors, ratings in archetype_data.items():
        if len(colors) != 2:  # Only two-color archetypes
            continue

        for rating in ratings:
            if rating.get("name") == card.name:
                games = rating.get("ever_drawn_game_count", 0) or 0
                # Use ever_drawn_win_rate for consistency with gih_wr
                wr = rating.get("ever_drawn_win_rate")
                if wr is not None and games >= min_games:
                    archetype_wrs[colors] = wr
                break

    # No archetype data at all
    if not archetype_wrs:
        return 0, None, 0.0, None

    # Find best archetype
    best_wr = max(archetype_wrs.values())
    best_archetype = max(archetype_wrs.keys(), key=lambda k: archetype_wrs[k])

    # For cards with only 1 archetype (typically gold cards committed to their color pair),
    # they are viable in that one archetype by definition
    if len(archetype_wrs) == 1:
        return 1, best_archetype, 0.0, None

    # Calculate viable archetypes (within 5% of best WR)
    viable_threshold = best_wr - 0.05
    viable_archs = [c for c, wr in archetype_wrs.items() if wr >= viable_threshold]
    viable_count = len(viable_archs)

    # Calculate off-archetype penalty (average WR drop in non-viable archetypes)
    non_viable_wrs = [wr for c, wr in archetype_wrs.items() if c not in viable_archs]
    if non_viable_wrs:
        off_penalty = best_wr - statistics.mean(non_viable_wrs)
    else:
        off_penalty = 0.0

    # Calculate natural premium (performance in card's natural colors vs others)
    card_colors = card.colors
    if card_colors:
        natural_archs = [c for c in archetype_wrs.keys() if any(color in c for color in card_colors)]
        other_archs = [c for c in archetype_wrs.keys() if c not in natural_archs]

        if natural_archs and other_archs:
            natural_avg = statistics.mean(archetype_wrs[c] for c in natural_archs)
            other_avg = statistics.mean(archetype_wrs[c] for c in other_archs)
            natural_premium = natural_avg - other_avg
        else:
            natural_premium = None
    else:
        natural_premium = None

    return viable_count, best_archetype, off_penalty, natural_premium


def enrich_cards_with_viability(
    cards: list[Card],
    archetype_data: dict[str, list[dict]],
    min_games: int = 50,
) -> list[Card]:
    """
    Enrich all cards with viability metrics.

    Viability provides practical information about how flexibly a card
    can be used across different archetypes.

    Args:
        cards: Scored cards to enrich
        archetype_data: Dict of archetype -> card ratings
        min_games: Minimum games for archetype inclusion

    Returns:
        Cards with viability fields updated
    """
    for card in cards:
        # Skip cards with no win rate data
        if card.stats.gih_wr is None:
            continue

        viable_count, best_arch, off_penalty, natural_prem = calculate_viability(
            card.stats, archetype_data, min_games
        )

        card.viable_archetypes = viable_count
        card.best_archetype = best_arch
        card.off_archetype_penalty = off_penalty
        card.natural_premium = natural_prem

        # Also store archetype WRs in stats (for display purposes)
        for colors, ratings in archetype_data.items():
            if len(colors) != 2:
                continue
            for rating in ratings:
                if rating.get("name") == card.name:
                    games = rating.get("ever_drawn_game_count", 0) or 0
                    # Use ever_drawn_win_rate for consistency with gih_wr
                    wr = rating.get("ever_drawn_win_rate")
                    if wr is not None and games >= min_games:
                        card.stats.archetype_wrs[colors] = wr
                        card.stats.archetype_games[colors] = games
                    break

    viable_count = sum(1 for c in cards if c.viable_archetypes > 0)
    flexible_count = sum(1 for c in cards if c.viable_archetypes >= 3)
    logger.info(
        f"Viability analysis: {viable_count}/{len(cards)} with viability data, "
        f"{flexible_count} flexible (3+ archetypes)"
    )

    return cards


# Keep alias for backwards compatibility during transition
def enrich_cards_with_variance(
    cards: list[Card],
    archetype_data: dict[str, list[dict]],
    min_games: int = 50,
) -> list[Card]:
    """Deprecated: Use enrich_cards_with_viability instead."""
    return enrich_cards_with_viability(cards, archetype_data, min_games)
