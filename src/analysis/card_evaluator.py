"""Card evaluation utilities."""

import logging
from typing import Optional

from src.models.card import Card, Rarity
from src.models.meta import MetaSnapshot

logger = logging.getLogger(__name__)


class CardEvaluator:
    """Utilities for evaluating and comparing cards."""

    def __init__(self, snapshot: MetaSnapshot):
        """
        Initialize evaluator with a meta snapshot.

        Args:
            snapshot: MetaSnapshot to evaluate cards from
        """
        self.snapshot = snapshot
        self.cards_by_name = {c.name.lower(): c for c in snapshot.all_cards}

    def get_card(self, name: str) -> Optional[Card]:
        """Get card by name (case-insensitive)."""
        return self.cards_by_name.get(name.lower())

    def compare_cards(self, *names: str) -> list[Card]:
        """
        Compare multiple cards, sorted by score.

        Args:
            *names: Card names to compare

        Returns:
            Cards sorted by composite score (best first)
        """
        cards = []
        for name in names:
            card = self.get_card(name)
            if card:
                cards.append(card)
            else:
                logger.warning(f"Card not found: {name}")

        return sorted(cards, key=lambda c: c.composite_score, reverse=True)

    def get_best_commons(self, color: Optional[str] = None, top_n: int = 10) -> list[Card]:
        """Get best commons, optionally filtered by color."""
        commons = [
            c for c in self.snapshot.all_cards
            if c.rarity == Rarity.COMMON
            and (color is None or color in c.colors)
        ]
        return sorted(commons, key=lambda c: c.composite_score, reverse=True)[:top_n]

    def get_best_uncommons(self, color: Optional[str] = None, top_n: int = 5) -> list[Card]:
        """Get best uncommons, optionally filtered by color."""
        uncommons = [
            c for c in self.snapshot.all_cards
            if c.rarity == Rarity.UNCOMMON
            and (color is None or color in c.colors)
        ]
        return sorted(uncommons, key=lambda c: c.composite_score, reverse=True)[:top_n]

    def get_bombs(self, min_score: float = 80.0) -> list[Card]:
        """Get bomb-level cards (high score rares/mythics)."""
        return [
            c for c in self.snapshot.all_cards
            if c.rarity in (Rarity.RARE, Rarity.MYTHIC)
            and c.composite_score >= min_score
        ]

    def get_synergy_cards(self, archetype: str) -> list[Card]:
        """Get cards that overperform in a specific archetype."""
        return [
            c for c in self.snapshot.all_cards
            if c.is_synergy_dependent
            and archetype in c.stats.archetype_wrs
            and c.stats.archetype_wrs[archetype] > c.stats.gih_wr + 0.02
        ]

    def get_stable_cards(self, min_stability: float = 80.0) -> list[Card]:
        """Get cards that perform consistently across archetypes."""
        return [
            c for c in self.snapshot.all_cards
            if c.stability_score >= min_stability
        ]

    def suggest_pick(
        self,
        available: list[str],
        archetype: Optional[str] = None,
    ) -> Optional[Card]:
        """
        Suggest best pick from available cards.

        Args:
            available: List of available card names
            archetype: Current archetype (e.g., "WU") if any

        Returns:
            Best card to pick, or None
        """
        cards = [self.get_card(name) for name in available]
        cards = [c for c in cards if c is not None]

        if not cards:
            return None

        if archetype:
            # Prioritize cards that perform well in this archetype
            def archetype_adjusted_score(card: Card) -> float:
                base = card.composite_score
                arch_wr = card.stats.archetype_wrs.get(archetype)
                if arch_wr:
                    # Boost score if card performs above average in archetype
                    boost = (arch_wr - card.stats.gih_wr) * 100
                    return base + boost
                return base

            return max(cards, key=archetype_adjusted_score)
        else:
            # Default to composite score
            return max(cards, key=lambda c: c.composite_score)

    def format_card_summary(self, card: Card) -> str:
        """Generate a one-line summary of a card."""
        return (
            f"{card.name} ({card.colors}, {card.rarity.value}) - "
            f"Grade: {card.grade}, Score: {card.composite_score:.1f}, "
            f"GIH WR: {card.stats.gih_wr*100:.1f}%"
        )

    def format_comparison(self, cards: list[Card]) -> str:
        """Format a comparison of multiple cards."""
        if not cards:
            return "No cards to compare."

        lines = ["Card Comparison:", ""]
        for i, card in enumerate(cards, 1):
            lines.append(f"{i}. {self.format_card_summary(card)}")

        return "\n".join(lines)
