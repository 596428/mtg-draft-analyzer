"""Trophy deck analysis for 17lands data.

NOTE: As of January 2025, individual deck detail fetching has been removed
to avoid excessive API calls (previously 500+ calls per analysis).
Trophy analysis now uses only metadata from the trophy list endpoint.
Card usage data is obtained from archetype_ratings instead.
"""

import json
import logging
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from src.data.loader import SeventeenLandsLoader, normalize_color_pair
from src.data.set_metadata import _fetch_scryfall_cards

logger = logging.getLogger(__name__)

# Cache for Scryfall card data (card_name -> card_data)
_scryfall_card_cache: dict[str, dict[str, dict]] = {}  # {expansion: {card_name: card_data}}

# Basic lands to exclude from top card lists
BASIC_LANDS = {"Plains", "Island", "Swamp", "Mountain", "Forest"}


@dataclass
class TrophyDeck:
    """Represents a single 7-win trophy deck (metadata only).

    NOTE: As of January 2025, this class only stores metadata from the
    trophy list endpoint. Individual deck card lists are no longer fetched
    to avoid excessive API calls.
    """

    aggregate_id: str
    deck_index: int
    colors: str
    wins: int
    losses: int
    timestamp: str

    @classmethod
    def from_api_data(cls, trophy_data: dict) -> "TrophyDeck":
        """Create TrophyDeck from trophy list API response data."""
        return cls(
            aggregate_id=trophy_data.get("aggregate_id", ""),
            deck_index=trophy_data.get("deck_index", 0),
            colors=normalize_color_pair(trophy_data.get("colors", "")),
            wins=trophy_data.get("wins", 0),
            losses=trophy_data.get("losses", 0),
            timestamp=trophy_data.get("time", ""),
        )


@dataclass
class ArchetypeTrophyStats:
    """Trophy statistics for a single archetype (metadata-based).

    NOTE: Card usage data is now populated from archetype_ratings API
    rather than individual deck fetching.
    """

    colors: str
    guild_name: str
    trophy_count: int = 0
    total_wins: int = 0
    total_losses: int = 0
    # Card usage from archetype_ratings (not individual deck fetching)
    card_usage: Counter = field(default_factory=Counter)
    card_usage_by_rarity: dict = field(default_factory=lambda: {
        "mythic": Counter(), "rare": Counter(),
        "uncommon": Counter(), "common": Counter(),
    })
    # CMC distribution from archetype_ratings card data (using Scryfall for CMC lookup)
    cmc_distribution: Counter = field(default_factory=Counter)  # "1", "2", "3", "4", "5", "6+"
    avg_cmc: float = 0.0  # Average CMC of cards in archetype
    # Creature stats from archetype_ratings (using Scryfall for type lookup)
    avg_creature_count: float = 0.0  # Average creature card count per deck (estimated)
    # Splash rate placeholder (can be estimated from 3-color decks)
    splash_rate: float = 0.0

    @property
    def win_rate(self) -> float:
        """Calculate average win rate of trophy decks."""
        total = self.total_wins + self.total_losses
        return self.total_wins / total if total > 0 else 0.0

    @property
    def trophy_share(self) -> float:
        """Placeholder for share calculation (set externally)."""
        return 0.0

    def top_cards(self, n: int = 10) -> list[tuple[str, int]]:
        """Get top N most-used cards in this archetype."""
        return self.card_usage.most_common(n)

    def top_cards_nonland(self, n: int = 10) -> list[dict]:
        """Get top N most-used cards excluding basic lands."""
        filtered = [
            (name, count) for name, count in self.card_usage.most_common(n * 2)
            if name not in BASIC_LANDS
        ][:n]
        return [
            {
                "name": name,
                "count": count,
                "per_deck_pct": round(count / self.trophy_count * 100) if self.trophy_count else 0,
            }
            for name, count in filtered
        ]

    def top_cards_by_rarity(self, *rarities: str, n: int = 10) -> list[dict]:
        """Get top cards filtered by one or more rarities (excluding basic lands).

        Args:
            *rarities: One or more rarity strings ('mythic', 'rare', 'uncommon', 'common')
            n: Number of cards to return

        Returns:
            List of dicts with name, count, per_deck_pct
        """
        combined = Counter()
        for r in rarities:
            combined.update(self.card_usage_by_rarity.get(r.lower(), Counter()))

        filtered = [
            (name, count) for name, count in combined.most_common(n * 2)
            if name not in BASIC_LANDS
        ][:n]
        return [
            {
                "name": name,
                "count": count,
                "per_deck_pct": round(count / self.trophy_count * 100) if self.trophy_count else 0,
            }
            for name, count in filtered
        ]


@dataclass
class TrophyStats:
    """Overall trophy deck statistics for a format (metadata-based).

    NOTE: This class now only stores trophy metadata from the trophy list endpoint.
    Card usage data is populated from archetype_ratings API, not individual deck fetching.
    """

    expansion: str
    format: str
    total_trophy_decks: int = 0
    analyzed_decks: int = 0
    archetype_stats: dict[str, ArchetypeTrophyStats] = field(default_factory=dict)
    overall_card_usage: Counter = field(default_factory=Counter)

    def get_archetype_ranking(self) -> list[ArchetypeTrophyStats]:
        """Get archetypes ranked by trophy count."""
        return sorted(
            self.archetype_stats.values(),
            key=lambda x: x.trophy_count,
            reverse=True,
        )

    def get_top_cards_overall(self, n: int = 20) -> list[tuple[str, int]]:
        """Get top N most-used cards across all archetypes (from archetype_ratings)."""
        return self.overall_card_usage.most_common(n)

    def get_archetype_share(self, colors: str) -> float:
        """Get trophy share for an archetype."""
        if self.analyzed_decks == 0:
            return 0.0
        stats = self.archetype_stats.get(colors)
        if not stats:
            return 0.0
        return stats.trophy_count / self.analyzed_decks

    def get_archetype(self, colors: str) -> Optional[ArchetypeTrophyStats]:
        """Get archetype stats by colors."""
        return self.archetype_stats.get(colors)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export and caching."""
        archetype_ranking = []
        for arch in self.get_archetype_ranking():
            arch_data = {
                "colors": arch.colors,
                "guild_name": arch.guild_name,
                "trophy_count": arch.trophy_count,
                "trophy_share_pct": round(arch.trophy_count / self.analyzed_decks * 100, 1) if self.analyzed_decks else 0,
                "total_wins": arch.total_wins,
                "total_losses": arch.total_losses,
                "win_rate_pct": round(arch.win_rate * 100, 1),
                # CMC stats (from archetype_ratings + Scryfall)
                "avg_cmc": round(arch.avg_cmc, 2) if arch.avg_cmc else None,
                "cmc_distribution": dict(arch.cmc_distribution),
                # Creature stats (from archetype_ratings + Scryfall)
                "avg_creature_count": round(arch.avg_creature_count, 1),
                # Splash stats
                "splash_rate_pct": round(arch.splash_rate * 100, 1),
                # Card usage (from archetype_ratings)
                "card_usage": dict(arch.card_usage),
                "card_usage_by_rarity": {
                    rarity: dict(counter) for rarity, counter in arch.card_usage_by_rarity.items()
                },
                "top_cards": [
                    {
                        "name": name,
                        "count": count,
                        "per_deck_avg": round(count / arch.trophy_count, 2) if arch.trophy_count else 0,
                    }
                    for name, count in arch.card_usage.most_common(20)
                    if name not in BASIC_LANDS
                ][:20],
            }
            archetype_ranking.append(arch_data)

        # Filter out basic lands from overall card usage for display
        filtered_card_usage = {
            k: v for k, v in self.overall_card_usage.items()
            if k not in BASIC_LANDS
        }

        return {
            "meta": {
                "expansion": self.expansion,
                "format": self.format,
                "analyzed_at": datetime.now().isoformat(),
                "total_trophy_decks": self.total_trophy_decks,
                "analyzed_decks": self.analyzed_decks,
                "note": "Card usage from archetype_ratings API (not individual deck fetching)",
            },
            "overall_card_usage": dict(self.overall_card_usage),
            "archetype_ranking": archetype_ranking,
            "overall_top_cards": [
                {
                    "name": name,
                    "count": count,
                    "appearance_rate_pct": round(count / self.analyzed_decks * 100, 1) if self.analyzed_decks else 0,
                }
                for name, count in Counter(filtered_card_usage).most_common(50)
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TrophyStats":
        """Reconstruct TrophyStats from cached dictionary.

        Args:
            data: Dictionary from to_dict() or cache file

        Returns:
            Reconstructed TrophyStats instance
        """
        meta = data.get("meta", {})
        stats = cls(
            expansion=meta.get("expansion", ""),
            format=meta.get("format", ""),
            total_trophy_decks=meta.get("total_trophy_decks", 0),
            analyzed_decks=meta.get("analyzed_decks", 0),
        )

        # Reconstruct overall card usage
        stats.overall_card_usage = Counter(data.get("overall_card_usage", {}))

        # Reconstruct archetype stats
        for arch_data in data.get("archetype_ranking", []):
            arch = ArchetypeTrophyStats(
                colors=arch_data.get("colors", ""),
                guild_name=arch_data.get("guild_name", ""),
                trophy_count=arch_data.get("trophy_count", 0),
                total_wins=arch_data.get("total_wins", 0),
                total_losses=arch_data.get("total_losses", 0),
                card_usage=Counter(arch_data.get("card_usage", {})),
                cmc_distribution=Counter(arch_data.get("cmc_distribution", {})),
                avg_cmc=arch_data.get("avg_cmc", 0.0) or 0.0,
                avg_creature_count=arch_data.get("avg_creature_count", 0.0),
                splash_rate=arch_data.get("splash_rate_pct", 0.0) / 100.0 if arch_data.get("splash_rate_pct") else 0.0,
            )
            # Reconstruct rarity-based card usage
            if arch_data.get("card_usage_by_rarity"):
                for rarity, card_dict in arch_data["card_usage_by_rarity"].items():
                    arch.card_usage_by_rarity[rarity] = Counter(card_dict)

            stats.archetype_stats[arch.colors] = arch

        return stats


# Guild name mapping
GUILD_NAMES = {
    "WU": "Azorius",
    "UB": "Dimir",
    "BR": "Rakdos",
    "RG": "Gruul",
    "WG": "Selesnya",
    "WB": "Orzhov",
    "UR": "Izzet",
    "BG": "Golgari",
    "WR": "Boros",
    "UG": "Simic",
}


def get_guild_name(colors: str) -> str:
    """Get guild name for a color pair."""
    normalized = normalize_color_pair(colors)
    if normalized in GUILD_NAMES:
        return GUILD_NAMES[normalized]
    # For 3+ color combos, just return the colors
    return colors


class TrophyAnalyzer:
    """Analyzes trophy deck data from 17lands.

    NOTE: As of January 2025, this analyzer no longer fetches individual deck details.
    Trophy analysis uses only metadata from the trophy list endpoint.
    Card usage data is populated from archetype_ratings API.
    """

    def __init__(
        self,
        loader: Optional[SeventeenLandsLoader] = None,
        max_decks: int = 500,
    ):
        """
        Initialize trophy analyzer.

        Args:
            loader: 17lands data loader
            max_decks: Maximum number of decks to analyze (metadata only, no rate limiting needed)
        """
        self.loader = loader or SeventeenLandsLoader()
        self.max_decks = max_decks

    def analyze(
        self,
        expansion: str,
        format: str = "PremierDraft",
        archetype_ratings: Optional[dict[str, list[dict]]] = None,
    ) -> TrophyStats:
        """
        Analyze trophy decks for a format (metadata only).

        This method no longer fetches individual deck details to avoid excessive API calls.
        Card usage data should be provided via archetype_ratings parameter.

        Args:
            expansion: Set code
            format: Draft format
            archetype_ratings: Optional dict mapping color code to card ratings list
                               from 17lands archetype_ratings API. Used to populate
                               card usage data.

        Returns:
            TrophyStats with analysis results
        """
        stats = TrophyStats(expansion=expansion, format=format)

        # Fetch trophy deck list (single API call)
        trophy_list = self.loader.fetch_trophy_decks(expansion, format)
        stats.total_trophy_decks = len(trophy_list)

        if not trophy_list:
            logger.warning(f"No trophy decks found for {expansion} {format}")
            return stats

        # Analyze decks (metadata only - no individual deck fetching)
        decks_to_analyze = trophy_list[: self.max_decks]
        archetype_decks: dict[str, list[TrophyDeck]] = defaultdict(list)

        for trophy_data in decks_to_analyze:
            deck = TrophyDeck.from_api_data(trophy_data)
            archetype_decks[deck.colors].append(deck)

        stats.analyzed_decks = len(decks_to_analyze)

        # Build archetype stats from trophy metadata
        for colors, decks in archetype_decks.items():
            arch_stats = ArchetypeTrophyStats(
                colors=colors,
                guild_name=get_guild_name(colors),
                trophy_count=len(decks),
            )

            for deck in decks:
                arch_stats.total_wins += deck.wins
                arch_stats.total_losses += deck.losses

            stats.archetype_stats[colors] = arch_stats

        # Populate card usage from archetype_ratings if provided
        if archetype_ratings:
            self._populate_card_usage_from_ratings(stats, archetype_ratings)

        logger.info(
            f"Trophy analysis complete: {stats.analyzed_decks} decks, "
            f"{len(stats.archetype_stats)} archetypes (metadata only)"
        )

        return stats

    def _get_scryfall_card_data(self, expansion: str) -> dict[str, dict]:
        """
        Get Scryfall card data for an expansion (cached).

        Returns:
            Dict mapping card name to Scryfall card data
        """
        global _scryfall_card_cache

        exp_upper = expansion.upper()
        if exp_upper not in _scryfall_card_cache:
            logger.info(f"Fetching Scryfall card data for {expansion}")
            cards = _fetch_scryfall_cards(expansion)
            _scryfall_card_cache[exp_upper] = {
                card.get("name", ""): card for card in cards
            }
            logger.info(f"Cached {len(_scryfall_card_cache[exp_upper])} cards from Scryfall")

        return _scryfall_card_cache[exp_upper]

    def _populate_card_usage_from_ratings(
        self,
        stats: TrophyStats,
        archetype_ratings: dict[str, list[dict]],
    ) -> None:
        """
        Populate card usage data from archetype_ratings API + Scryfall.

        This replaces the old method of fetching individual deck details.
        - Card usage is estimated based on game_count from 17lands
        - CMC is fetched from Scryfall
        - Creature type is detected from 17lands 'types' array or Scryfall

        Args:
            stats: TrophyStats to populate
            archetype_ratings: Dict mapping color code to card ratings list
        """
        # Get Scryfall card data for CMC lookup
        scryfall_cards = self._get_scryfall_card_data(stats.expansion)

        for colors, arch_stats in stats.archetype_stats.items():
            # Find matching archetype ratings
            ratings = archetype_ratings.get(colors, [])
            if not ratings:
                logger.debug(f"No archetype ratings found for {colors}")
                continue

            # Calculate CMC distribution and creature count using game_count
            # game_count = number of decks that included this card
            cmc_counts = Counter()  # CMC bucket -> total game_count
            total_cmc_weighted = 0.0
            total_game_count = 0  # Sum of game_count for all nonland cards
            creature_game_count = 0  # Sum of game_count for creature cards

            for card_data in ratings:
                name = card_data.get("name", "")
                if not name or name in BASIC_LANDS:
                    continue

                rarity = (card_data.get("rarity") or "unknown").lower()

                # game_count = how many decks included this card
                game_count = card_data.get("game_count", 0)
                if game_count <= 0:
                    continue

                # Track card usage (normalized for display)
                usage_weight = min(game_count / 1000, arch_stats.trophy_count)
                arch_stats.card_usage[name] += int(usage_weight)
                stats.overall_card_usage[name] += int(usage_weight)

                if rarity in arch_stats.card_usage_by_rarity:
                    arch_stats.card_usage_by_rarity[rarity][name] += int(usage_weight)

                # Get CMC from Scryfall (17lands doesn't have CMC)
                scryfall_card = scryfall_cards.get(name, {})
                cmc = scryfall_card.get("cmc", 0)
                if cmc is None:
                    cmc = 0

                # CMC distribution - use game_count as weight
                if isinstance(cmc, (int, float)) and cmc >= 0:
                    if cmc <= 1:
                        cmc_counts["1"] += game_count
                    elif cmc == 2:
                        cmc_counts["2"] += game_count
                    elif cmc == 3:
                        cmc_counts["3"] += game_count
                    elif cmc == 4:
                        cmc_counts["4"] += game_count
                    elif cmc == 5:
                        cmc_counts["5"] += game_count
                    else:
                        cmc_counts["6+"] += game_count

                    total_cmc_weighted += cmc * game_count
                    total_game_count += game_count

                # Check if creature from 17lands 'types' array or Scryfall
                is_creature = False
                types = card_data.get("types", [])
                if not types:
                    # Fallback to Scryfall type_line
                    type_line = scryfall_card.get("type_line", "")
                    if "Creature" in type_line:
                        is_creature = True
                else:
                    # Check 17lands types array
                    for t in types:
                        if "Creature" in t:
                            is_creature = True
                            break

                if is_creature:
                    creature_game_count += game_count

            # Set CMC stats
            arch_stats.cmc_distribution = cmc_counts
            if total_game_count > 0:
                arch_stats.avg_cmc = total_cmc_weighted / total_game_count

            # Calculate average creature count per deck
            # creature_ratio = creature inclusions / total card inclusions
            # Typical draft deck has ~23 nonland cards
            if total_game_count > 0:
                creature_ratio = creature_game_count / total_game_count
                # Multiply by typical nonland card count (23) to get creature count
                arch_stats.avg_creature_count = round(creature_ratio * 23, 1)

    def save_to_cache(
        self,
        stats: TrophyStats,
        output_dir: str = "output",
    ) -> str:
        """Save trophy stats to cache file.

        Args:
            stats: TrophyStats to cache
            output_dir: Output directory

        Returns:
            Path to cache file
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        cache_file = output_path / f"{stats.expansion}_{stats.format}_trophy_cache.json"

        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(stats.to_dict(), f, ensure_ascii=False, indent=2)

        logger.info(f"Trophy cache saved to {cache_file}")
        return str(cache_file)

    @staticmethod
    def load_from_cache(
        expansion: str,
        format: str = "PremierDraft",
        output_dir: str = "output",
        max_age_days: int = 7,
    ) -> Optional[TrophyStats]:
        """Load trophy stats from cache file if valid.

        Args:
            expansion: Set code
            format: Draft format
            output_dir: Directory containing cache files
            max_age_days: Maximum age of cache in days (default 7)

        Returns:
            TrophyStats if cache is valid, None otherwise
        """
        cache_file = Path(output_dir) / f"{expansion}_{format}_trophy_cache.json"

        if not cache_file.exists():
            logger.debug(f"Trophy cache not found: {cache_file}")
            return None

        # Check cache age
        file_mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
        age_days = (datetime.now() - file_mtime).days

        if age_days > max_age_days:
            logger.info(f"Trophy cache expired ({age_days} days old): {cache_file}")
            return None

        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            stats = TrophyStats.from_dict(data)
            logger.info(
                f"Loaded trophy cache: {stats.analyzed_decks} decks, "
                f"{len(stats.archetype_stats)} archetypes ({age_days} days old)"
            )
            return stats

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Failed to load trophy cache: {e}")
            return None


def analyze_trophy_decks(
    expansion: str,
    format: str = "PremierDraft",
    max_decks: int = 500,
    archetype_ratings: Optional[dict[str, list[dict]]] = None,
) -> TrophyStats:
    """
    Convenience function to analyze trophy decks (metadata only).

    Args:
        expansion: Set code
        format: Draft format
        max_decks: Maximum decks to analyze (metadata only)
        archetype_ratings: Optional archetype ratings for card usage data

    Returns:
        TrophyStats with analysis results
    """
    analyzer = TrophyAnalyzer(max_decks=max_decks)
    return analyzer.analyze(expansion, format, archetype_ratings)
