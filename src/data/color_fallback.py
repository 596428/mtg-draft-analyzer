"""Fallback computation for color pair win rates when API fails."""

import logging
from collections import defaultdict

from src.models.archetype import COLOR_PAIRS, ColorPair, ALL_ARCHETYPE_NAMES
from src.models.card import CardStats

logger = logging.getLogger(__name__)


def compute_color_pairs_from_cards(
    card_stats: list[CardStats],
    min_games: int = 200,
    primary_weight: float = 0.7,
) -> list[ColorPair]:
    """
    Compute archetype win rates using hybrid algorithm.

    Primary Signal (70%): Gold card deck_wr
    Secondary Signal (30%): Overperforming mono-color card deck_wr

    Args:
        card_stats: List of CardStats from fetch_card_ratings
        min_games: Minimum game count for card inclusion
        primary_weight: Weight for gold card signal (default 0.7)

    Returns:
        List of ColorPair objects sorted by win rate, with is_computed=True
    """
    if not card_stats:
        logger.warning("No card stats provided for fallback computation")
        return []

    # Filter cards with valid deck_wr data
    valid_cards = [
        c for c in card_stats
        if c.deck_wr is not None and c.deck_wr > 0 and c.game_count >= min_games
    ]

    if not valid_cards:
        logger.warning("No cards with deck_wr data for fallback")
        return []

    logger.info(f"Computing fallback with {len(valid_cards)} valid cards")

    # Step 1: Calculate average deck_wr for each single color
    color_avg = _calculate_color_averages(valid_cards)

    # Step 2: Identify overperforming mono-color cards
    overperformers = _get_overperformers(valid_cards, color_avg)

    # Step 3: Identify viable archetypes dynamically
    # Start with standard 2-color pairs
    target_archetypes = set(COLOR_PAIRS)

    # Check for 3-color gold cards to detect wedges/shards
    for card in valid_cards:
        if len(card.colors) == 3:
            # If we have valid 3-color cards, add their colors to targets
            target_archetypes.add(card.colors)

    logger.info(f"Identified {len(target_archetypes)} potential archetypes for analysis")

    # Step 4: Calculate hybrid archetype win rates
    results = []
    for colors in target_archetypes:
        hybrid_wr, gold_count, mono_count, total_games = _calculate_hybrid_wr(
            colors, valid_cards, overperformers, primary_weight
        )

        if hybrid_wr is None:
            continue

        results.append(ColorPair(
            colors=colors,
            wins=int(hybrid_wr * total_games),  # Estimated wins
            games=total_games,  # Sum of game counts from cards used
            win_rate=hybrid_wr,
            is_computed=True,
        ))

    # Sort by win rate descending
    results.sort(key=lambda x: x.win_rate, reverse=True)

    logger.info(f"Computed {len(results)} color pairs using hybrid algorithm")
    return results


def _calculate_color_averages(cards: list[CardStats]) -> dict[str, float]:
    """
    Calculate average deck_wr for each single color.

    Args:
        cards: List of CardStats with valid deck_wr

    Returns:
        Dict mapping single color (e.g., "W", "U") to average deck_wr
    """
    color_wrs: dict[str, list[float]] = defaultdict(list)

    for card in cards:
        # Only consider mono-color cards
        if len(card.colors) == 1:
            color_wrs[card.colors].append(card.deck_wr)

    return {
        color: sum(wrs) / len(wrs)
        for color, wrs in color_wrs.items()
        if wrs
    }


def _get_overperformers(
    cards: list[CardStats],
    color_avg: dict[str, float],
) -> dict[str, list[CardStats]]:
    """
    Get mono-color cards with deck_wr above their color's average.

    These cards represent strong performers in their color that likely
    contribute to archetype success.

    Args:
        cards: List of CardStats with valid deck_wr
        color_avg: Dict of color -> average deck_wr

    Returns:
        Dict mapping single color to list of overperforming CardStats
    """
    overperformers: dict[str, list[CardStats]] = defaultdict(list)

    for card in cards:
        if len(card.colors) == 1 and card.colors in color_avg:
            if card.deck_wr > color_avg[card.colors]:
                overperformers[card.colors].append(card)

    return overperformers


def _calculate_hybrid_wr(
    colors: str,
    all_cards: list[CardStats],
    overperformers: dict[str, list[CardStats]],
    primary_weight: float,
) -> tuple[float | None, int, int, int]:
    """
    Calculate hybrid win rate for an archetype.

    Hybrid WR = primary_weight * gold_wr + (1 - primary_weight) * mono_wr

    Args:
        colors: Two-color archetype string (e.g., "WU", "GW")
        all_cards: All valid cards
        overperformers: Dict of color -> overperforming cards
        primary_weight: Weight for gold card signal

    Returns:
        Tuple of (hybrid_wr, gold_card_count, mono_card_count, total_games)
        Returns (None, 0, 0, 0) if no data available
    """
    color_set = set(colors)

    # Primary signal: Gold cards (exact color match)
    gold_cards = [c for c in all_cards if set(c.colors) == color_set]

    if gold_cards:
        gold_games = sum(c.game_count for c in gold_cards)
        gold_wr = sum(c.deck_wr * c.game_count for c in gold_cards) / gold_games
    else:
        gold_wr = None
        gold_games = 0

    # Secondary signal: Overperforming mono-color cards from both colors
    c1, c2 = colors[0], colors[1]
    mono_cards = overperformers.get(c1, []) + overperformers.get(c2, [])

    if mono_cards:
        mono_games = sum(c.game_count for c in mono_cards)
        mono_wr = sum(c.deck_wr * c.game_count for c in mono_cards) / mono_games
    else:
        mono_wr = None
        mono_games = 0

    total_games = gold_games + mono_games

    # Calculate hybrid WR with fallback logic
    if gold_wr is not None and mono_wr is not None:
        hybrid_wr = primary_weight * gold_wr + (1 - primary_weight) * mono_wr
        return hybrid_wr, len(gold_cards), len(mono_cards), total_games
    elif gold_wr is not None:
        # Only gold cards available
        return gold_wr, len(gold_cards), 0, gold_games
    elif mono_wr is not None:
        # Only mono overperformers available
        return mono_wr, 0, len(mono_cards), mono_games
    else:
        # No data available
        return None, 0, 0, 0
