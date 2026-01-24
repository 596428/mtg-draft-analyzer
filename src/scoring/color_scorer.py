"""Color and archetype strength scoring."""

import logging
import statistics
from typing import Optional

import yaml

from src.models.archetype import (
    COLOR_PAIRS,
    Archetype,
    ColorPair,
    ColorStrength,
)
from src.models.card import Card, Rarity

logger = logging.getLogger(__name__)

# Single colors
COLORS = ["W", "U", "B", "R", "G"]


class ColorScorer:
    """Calculates strength scores for colors and archetypes."""

    DEFAULT_WEIGHTS = {
        "deck_wr_strength": 0.35,
        "archetype_success": 0.25,
        "top_common_avg": 0.15,
        "top_uncommon_avg": 0.10,
        "bomb_factor": 0.10,
        "depth_factor": 0.05,
    }

    DEFAULT_TOP_N = {
        "common": 10,
        "uncommon": 5,
        "rare": 3,
    }

    def __init__(
        self,
        weights: Optional[dict[str, float]] = None,
        top_n: Optional[dict[str, int]] = None,
        stability_weight_min: float = 0.80,
        stability_weight_max: float = 1.00,
        playable_threshold: float = 50.0,
    ):
        """
        Initialize color scorer.

        Args:
            weights: Component weights for strength calculation
            top_n: Number of top cards to consider per rarity
            stability_weight_min: Weight for synergy-dependent cards
            stability_weight_max: Weight for stable cards
            playable_threshold: Minimum score to count as playable
        """
        self.weights = weights or self.DEFAULT_WEIGHTS
        self.top_n = top_n or self.DEFAULT_TOP_N
        self.stability_weight_min = stability_weight_min
        self.stability_weight_max = stability_weight_max
        self.playable_threshold = playable_threshold

    @classmethod
    def from_config(cls, config_path: str = "config/scoring.yaml") -> "ColorScorer":
        """Create scorer from YAML config file."""
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        cs_config = config.get("color_strength", {})
        return cls(
            weights=cs_config.get("weights"),
            top_n=cs_config.get("top_n"),
            stability_weight_min=cs_config.get("stability_weight", {}).get("min", 0.80),
            stability_weight_max=cs_config.get("stability_weight", {}).get("max", 1.00),
        )

    def _get_color_cards(self, color: str, cards: list[Card]) -> list[Card]:
        """Get all cards containing a specific color."""
        return [c for c in cards if color in c.colors]

    def _get_stability_weight(self, card: Card) -> float:
        """
        Calculate stability weight for a card.

        Stable cards get weight of 1.0, synergy-dependent cards get reduced weight.
        """
        # Linear interpolation based on stability score
        normalized = card.stability_score / 100.0
        return self.stability_weight_min + normalized * (
            self.stability_weight_max - self.stability_weight_min
        )

    def _calculate_top_avg(
        self,
        cards: list[Card],
        rarity: Rarity,
        top_n: int,
    ) -> tuple[float, list[str]]:
        """Calculate average score of top N cards of a rarity."""
        rarity_cards = [c for c in cards if c.rarity == rarity]
        rarity_cards.sort(key=lambda c: c.composite_score, reverse=True)

        top_cards = rarity_cards[:top_n]

        if not top_cards:
            return 0.0, []

        # Apply stability weighting
        weighted_scores = [
            c.composite_score * self._get_stability_weight(c)
            for c in top_cards
        ]

        avg = statistics.mean(weighted_scores)
        names = [c.name for c in top_cards]

        return avg, names

    def _calculate_bomb_factor(self, cards: list[Card]) -> tuple[float, list[str]]:
        """Calculate bomb factor from rare/mythic cards."""
        rare_mythic = [
            c for c in cards
            if c.rarity in (Rarity.RARE, Rarity.MYTHIC)
        ]

        if not rare_mythic:
            return 0.0, []

        # Get top rares/mythics
        top_n = self.top_n.get("rare", 3)
        rare_mythic.sort(key=lambda c: c.composite_score, reverse=True)
        top_bombs = rare_mythic[:top_n]

        # Bomb factor based on score above threshold
        bomb_scores = [
            max(0, c.composite_score - 70)  # Only count scores above 70
            for c in top_bombs
        ]

        factor = sum(bomb_scores) / (top_n * 30)  # Normalize to 0-1
        factor = min(1.0, factor)  # Cap at 1.0

        names = [c.name for c in top_bombs]

        return factor * 100, names  # Scale to 0-100

    def _calculate_depth_factor(self, cards: list[Card]) -> float:
        """Calculate depth factor (number of playable cards)."""
        playable = [c for c in cards if c.composite_score >= self.playable_threshold]

        # More playables = better depth
        # Normalize: 20 playables = 100, 10 = 50, etc.
        return min(100, len(playable) * 5)

    def _calculate_deck_wr_strength(self, color: str, cards: list[Card]) -> float:
        """
        Calculate color strength from deck win rates of mono-color cards.

        Uses mono-color cards only because:
        - Multi-color cards belong to specific archetypes
        - Mono-color cards are used across all decks of that color

        Args:
            color: Single color (W, U, B, R, G)
            cards: Cards containing this color

        Returns:
            Deck win rate strength scaled to 0-100
        """
        mono_cards = [
            c for c in cards
            if c.colors == color
            and c.stats.deck_wr > 0
            and c.stats.game_count >= 200
        ]

        if not mono_cards:
            return 50.0

        # Game-weighted average for statistical reliability
        total_games = sum(c.stats.game_count for c in mono_cards)
        deck_wr = sum(c.stats.deck_wr * c.stats.game_count for c in mono_cards) / total_games

        return deck_wr * 100

    def calculate_color_strength(
        self,
        color: str,
        cards: list[Card],
        color_pairs: Optional[list[ColorPair]] = None,
    ) -> ColorStrength:
        """
        Calculate strength score for a single color.

        Args:
            color: Single color (W, U, B, R, G)
            cards: All scored cards
            color_pairs: Color pair data for archetype success

        Returns:
            ColorStrength object
        """
        color_cards = self._get_color_cards(color, cards)

        if not color_cards:
            return ColorStrength(color=color)

        # Calculate component scores
        top_common_avg, top_commons = self._calculate_top_avg(
            color_cards, Rarity.COMMON, self.top_n.get("common", 10)
        )

        top_uncommon_avg, top_uncommons = self._calculate_top_avg(
            color_cards, Rarity.UNCOMMON, self.top_n.get("uncommon", 5)
        )

        bomb_factor, top_rares = self._calculate_bomb_factor(color_cards)
        depth_factor = self._calculate_depth_factor(color_cards)

        # Calculate deck WR strength (direct performance indicator)
        deck_wr_strength = self._calculate_deck_wr_strength(color, color_cards)

        # Calculate archetype success (average of color pairs containing this color)
        archetype_success = 0.0
        if color_pairs:
            relevant_pairs = [
                cp for cp in color_pairs
                if color in cp.colors and len(cp.colors) == 2
            ]
            if relevant_pairs:
                archetype_success = (
                    statistics.mean(cp.win_rate for cp in relevant_pairs) * 100
                )

        # Calculate weighted strength score
        strength = (
            self.weights.get("deck_wr_strength", 0) * deck_wr_strength +
            self.weights.get("archetype_success", 0) * archetype_success +
            self.weights["top_common_avg"] * top_common_avg +
            self.weights["top_uncommon_avg"] * top_uncommon_avg +
            self.weights["bomb_factor"] * bomb_factor +
            self.weights["depth_factor"] * depth_factor
        )

        playable_count = len([
            c for c in color_cards
            if c.composite_score >= self.playable_threshold
        ])

        return ColorStrength(
            color=color,
            strength_score=strength,
            deck_wr_strength=deck_wr_strength,
            archetype_success=archetype_success,
            top_common_avg=top_common_avg,
            top_uncommon_avg=top_uncommon_avg,
            bomb_factor=bomb_factor,
            depth_factor=depth_factor,
            playable_count=playable_count,
            total_cards=len(color_cards),
            top_commons=top_commons,
            top_uncommons=top_uncommons,
            top_rares=top_rares,
        )

    def calculate_all_color_strengths(
        self,
        cards: list[Card],
        color_pairs: Optional[list[ColorPair]] = None,
    ) -> list[ColorStrength]:
        """
        Calculate strength for all colors.

        Args:
            cards: All scored cards
            color_pairs: Color pair data

        Returns:
            List of ColorStrength sorted by strength (best first)
        """
        strengths = []

        for color in COLORS:
            strength = self.calculate_color_strength(color, cards, color_pairs)
            strengths.append(strength)

        # Sort and assign ranks
        strengths.sort(key=lambda s: s.strength_score, reverse=True)
        for i, strength in enumerate(strengths):
            strength.rank = i + 1

        return strengths

    def _calculate_synergy_lift(
        self,
        card: Card,
        archetype_colors: str,
        archetype_avg_wr: float,
    ) -> float:
        """
        Calculate synergy lift for a card in an archetype.

        For mono-color cards: compares archetype WR to global GIH WR
        For multi-color cards: compares archetype WR to archetype average WR

        Args:
            card: Card to analyze
            archetype_colors: Two-color pair (e.g., "WG")
            archetype_avg_wr: Average win rate of the archetype

        Returns:
            Synergy lift value (positive = overperforms, negative = underperforms)
        """
        card_archetype_wr = card.stats.archetype_wrs.get(
            archetype_colors, card.stats.gih_wr
        )

        if len(card.colors) >= 2:
            # Multi-color card: compare to archetype average
            baseline = archetype_avg_wr
        else:
            # Mono-color card: compare to global GIH WR
            baseline = card.stats.gih_wr

        return card_archetype_wr - baseline

    def build_archetype(
        self,
        color_pair: ColorPair,
        cards: list[Card],
        all_color_pairs: list[ColorPair],
    ) -> Archetype:
        """
        Build archetype analysis for a color pair.

        Uses synergy lift calculation to evaluate how well cards work
        together in this archetype beyond their individual strength.

        Args:
            color_pair: Color pair to analyze
            cards: All scored cards
            all_color_pairs: All color pair data for comparison

        Returns:
            Archetype object
        """
        # Get cards in this archetype
        colors = color_pair.colors
        archetype_cards = [
            c for c in cards
            if all(color in c.colors for color in colors)
            or (len(c.colors) == 1 and c.colors in colors)
        ]

        # Find key cards by rarity
        commons = sorted(
            [c for c in archetype_cards if c.rarity == Rarity.COMMON],
            key=lambda c: c.composite_score,
            reverse=True,
        )
        uncommons = sorted(
            [c for c in archetype_cards if c.rarity == Rarity.UNCOMMON],
            key=lambda c: c.composite_score,
            reverse=True,
        )
        rares = sorted(
            [c for c in archetype_cards if c.rarity in (Rarity.RARE, Rarity.MYTHIC)],
            key=lambda c: c.composite_score,
            reverse=True,
        )

        # Calculate synergy lifts for all cards with archetype data
        archetype_avg_wr = color_pair.win_rate
        synergy_lifts = []
        for card in archetype_cards:
            if colors in card.stats.archetype_wrs:
                lift = self._calculate_synergy_lift(card, colors, archetype_avg_wr)
                synergy_lifts.append(lift)

        # Calculate synergy metrics
        avg_synergy_lift = statistics.mean(synergy_lifts) if synergy_lifts else 0
        synergy_std = (
            statistics.stdev(synergy_lifts) if len(synergy_lifts) > 1 else 0
        )
        # Ratio of cards with positive synergy (> 2% lift)
        synergy_card_ratio = (
            sum(1 for lift in synergy_lifts if lift > 0.02) / max(len(synergy_lifts), 1)
        )

        # Stability bonus: lower variance = more consistent synergy (0-5 points)
        stability_bonus = max(0, 5 - synergy_std * 100)

        # Find synergy cards (overperform in this pair)
        synergy_cards = [
            c.name for c in archetype_cards
            if colors in c.stats.archetype_wrs
            and c.stats.archetype_wrs.get(colors, 0) > c.stats.gih_wr + 0.02
        ]

        # Find trap cards (underperform in this pair)
        trap_cards = [
            c.name for c in archetype_cards
            if colors in c.stats.archetype_wrs
            and c.stats.archetype_wrs.get(colors, 0) < c.stats.gih_wr - 0.02
        ]

        # Calculate meta share (based on games)
        total_games = sum(cp.games for cp in all_color_pairs if len(cp.colors) == 2)
        meta_share = color_pair.games / total_games if total_games > 0 else 0

        # Calculate commons/uncommons score for formula
        commons_score = (
            statistics.mean(c.composite_score for c in commons[:5]) if commons else 0
        )
        uncommons_score = (
            statistics.mean(c.composite_score for c in uncommons[:3]) if uncommons else 0
        )

        # Calculate strength score with win rate as primary factor
        # Previous formula had synergy_lift * 200 which was way too high
        # New formula centers on win rate deviation from 50% baseline
        #
        # Components:
        # - Win rate deviation: (WR - 0.50) * 1000 → ±5% WR = ±50 points
        # - Synergy lift: avg_synergy_lift * 50 → 2% lift = 1 point
        # - Synergy density: ratio of synergy cards
        # - Card quality: commons and uncommons average scores
        # - Stability: consistency bonus
        strength = (
            (color_pair.win_rate - 0.50) * 1000 +  # WR deviation (primary)
            avg_synergy_lift * 50 +                 # Synergy contribution (reduced)
            synergy_card_ratio * 15 +               # Synergy density
            stability_bonus * 2 +                   # Consistency bonus (0-10)
            commons_score * 0.1 +                   # Common quality
            uncommons_score * 0.1                   # Uncommon quality
        )

        return Archetype(
            color_pair=color_pair,
            strength_score=strength,
            key_commons=[c.name for c in commons[:5]],
            key_uncommons=[c.name for c in uncommons[:3]],
            signpost_uncommon=uncommons[0].name if uncommons else None,
            bombs=[c.name for c in rares[:3]],
            synergy_cards=synergy_cards[:5],
            trap_cards=trap_cards[:3],
            meta_share=meta_share,
            synergy_lift=avg_synergy_lift,
            synergy_std=synergy_std,
        )

    def build_all_archetypes(
        self,
        cards: list[Card],
        color_pairs: list[ColorPair],
    ) -> list[Archetype]:
        """
        Build archetype analysis for all color pairs.

        Args:
            cards: All scored cards
            color_pairs: Color pair data

        Returns:
            List of Archetypes sorted by win rate
        """
        archetypes = []

        # Filter to only 2-color pairs
        two_color_pairs = [
            cp for cp in color_pairs
            if len(cp.colors) == 2 and cp.games >= 1000
        ]

        for color_pair in two_color_pairs:
            archetype = self.build_archetype(color_pair, cards, color_pairs)
            archetypes.append(archetype)

        # Sort by win rate and assign ranks
        archetypes.sort(key=lambda a: a.win_rate, reverse=True)
        for i, archetype in enumerate(archetypes):
            archetype.rank = i + 1

        return archetypes
