"""Trophy deck analysis for 17lands data."""

import logging
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Optional

from src.data.loader import SeventeenLandsLoader, normalize_color_pair

logger = logging.getLogger(__name__)


def parse_required_colors(mana_cost: str) -> set:
    """
    Parse mana cost string to identify truly required colors.

    Hybrid mana {A/B} means either A or B works, so neither is required.
    Only non-hybrid colored mana symbols are required.

    Examples:
        "{2}{W}{U}" -> {"W", "U"}  (both required)
        "{2}{W/U}{W/U}" -> set()   (neither required - hybrid)
        "{1}{W}{B/G}" -> {"W"}     (only W required)
        "{B}{B}" -> {"B"}          (B required)
    """
    if not mana_cost:
        return set()

    required = set()
    color_chars = {"W", "U", "B", "R", "G"}

    # Find all mana symbols in braces
    symbols = re.findall(r'\{([^}]+)\}', mana_cost)

    for symbol in symbols:
        # Skip hybrid mana (contains '/')
        if '/' in symbol:
            continue
        # Skip colorless/generic mana (numbers, X, C)
        if symbol.isdigit() or symbol in ('X', 'C', 'S'):
            continue
        # Check for color symbols
        for char in symbol:
            if char in color_chars:
                required.add(char)

    return required


@dataclass
class TrophyDeck:
    """Represents a single 7-win trophy deck."""

    aggregate_id: str
    deck_index: int
    colors: str
    wins: int
    losses: int
    timestamp: str
    maindeck_card_ids: list[int] = field(default_factory=list)
    maindeck_card_names: list[str] = field(default_factory=list)
    maindeck_card_cmcs: list[float] = field(default_factory=list)
    maindeck_card_colors: list[set] = field(default_factory=list)  # color_identity (for reference)
    maindeck_card_required_colors: list[set] = field(default_factory=list)  # actual required colors
    sideboard_card_ids: list[int] = field(default_factory=list)

    @property
    def avg_cmc(self) -> float:
        """Calculate average CMC of non-land cards."""
        # Filter out lands (CMC 0 with no color) - basic lands have CMC 0
        non_land_cmcs = [
            cmc for cmc, colors in zip(self.maindeck_card_cmcs, self.maindeck_card_colors)
            if cmc > 0 or colors  # Keep if CMC > 0 or has colors (colored 0-cost spells)
        ]
        return sum(non_land_cmcs) / len(non_land_cmcs) if non_land_cmcs else 0.0

    @property
    def splash_colors(self) -> set:
        """
        Identify splash colors (required colors in deck not in main colors).

        Uses mana_cost parsing to exclude hybrid mana cards.
        A color is only considered splash if it's REQUIRED (non-hybrid) and
        not in the deck's main colors.
        """
        main_colors = set(self.colors)
        required_colors = set()
        for card_required in self.maindeck_card_required_colors:
            required_colors.update(card_required)
        return required_colors - main_colors

    @property
    def is_splash(self) -> bool:
        """Check if deck contains splash colors."""
        return len(self.splash_colors) > 0

    @property
    def total_colors(self) -> int:
        """Total number of required colors in the deck."""
        all_colors = set(self.colors)
        for card_required in self.maindeck_card_required_colors:
            all_colors.update(card_required)
        return len(all_colors)

    @classmethod
    def from_api_data(
        cls,
        trophy_data: dict,
        deck_details: Optional[dict] = None,
    ) -> "TrophyDeck":
        """Create TrophyDeck from API response data."""
        deck = cls(
            aggregate_id=trophy_data.get("aggregate_id", ""),
            deck_index=trophy_data.get("deck_index", 0),
            colors=normalize_color_pair(trophy_data.get("colors", "")),
            wins=trophy_data.get("wins", 0),
            losses=trophy_data.get("losses", 0),
            timestamp=trophy_data.get("time", ""),
        )

        if deck_details:
            # Extract card IDs, names, CMC, and colors from deck details
            groups = deck_details.get("groups", [])
            cards_info = deck_details.get("cards", {})

            for group in groups:
                group_name = group.get("name", "")
                card_ids = group.get("cards", [])

                if group_name == "Maindeck":
                    deck.maindeck_card_ids = card_ids
                    # Map IDs to names, CMC, colors, and required colors
                    for card_id in card_ids:
                        card_data = cards_info.get(str(card_id), {})
                        name = card_data.get("name", f"Unknown_{card_id}")
                        cmc = card_data.get("cmc", 0.0)
                        color_identity = set(card_data.get("color_identity", []))
                        mana_cost = card_data.get("mana_cost", "")
                        required_colors = parse_required_colors(mana_cost)

                        deck.maindeck_card_names.append(name)
                        deck.maindeck_card_cmcs.append(cmc)
                        deck.maindeck_card_colors.append(color_identity)
                        deck.maindeck_card_required_colors.append(required_colors)
                elif group_name == "Sideboard":
                    deck.sideboard_card_ids = card_ids

        return deck


@dataclass
class SplashStats:
    """Splash pattern statistics."""

    total_decks: int = 0
    splash_decks: int = 0
    splash_by_color: Counter = field(default_factory=Counter)  # W, U, B, R, G
    three_color_decks: int = 0
    four_plus_color_decks: int = 0

    @property
    def splash_rate(self) -> float:
        """Percentage of decks that splash."""
        return self.splash_decks / self.total_decks if self.total_decks > 0 else 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "total_decks": self.total_decks,
            "splash_decks": self.splash_decks,
            "splash_rate_pct": round(self.splash_rate * 100, 1),
            "splash_by_color": dict(self.splash_by_color.most_common()),
            "three_color_decks": self.three_color_decks,
            "four_plus_color_decks": self.four_plus_color_decks,
        }


@dataclass
class CMCStats:
    """CMC distribution statistics."""

    avg_cmc: float = 0.0
    min_cmc: float = 0.0
    max_cmc: float = 0.0
    cmc_distribution: dict[str, int] = field(default_factory=dict)  # "1", "2", "3", "4", "5", "6+"

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "avg_cmc": round(self.avg_cmc, 2),
            "min_cmc": round(self.min_cmc, 2),
            "max_cmc": round(self.max_cmc, 2),
            "cmc_distribution": self.cmc_distribution,
        }


@dataclass
class ArchetypeTrophyStats:
    """Trophy statistics for a single archetype."""

    colors: str
    guild_name: str
    trophy_count: int = 0
    total_wins: int = 0
    total_losses: int = 0
    card_usage: Counter = field(default_factory=Counter)
    # CMC stats
    deck_cmcs: list[float] = field(default_factory=list)
    # Splash stats
    splash_count: int = 0
    splash_colors: Counter = field(default_factory=Counter)

    @property
    def win_rate(self) -> float:
        """Calculate average win rate of trophy decks."""
        total = self.total_wins + self.total_losses
        return self.total_wins / total if total > 0 else 0.0

    @property
    def avg_cmc(self) -> float:
        """Average CMC across all decks in this archetype."""
        return sum(self.deck_cmcs) / len(self.deck_cmcs) if self.deck_cmcs else 0.0

    @property
    def splash_rate(self) -> float:
        """Percentage of decks that splash in this archetype."""
        return self.splash_count / self.trophy_count if self.trophy_count > 0 else 0.0

    @property
    def trophy_share(self) -> float:
        """Placeholder for share calculation (set externally)."""
        return 0.0

    def top_cards(self, n: int = 10) -> list[tuple[str, int]]:
        """Get top N most-used cards in this archetype's trophy decks."""
        return self.card_usage.most_common(n)


@dataclass
class TrophyStats:
    """Overall trophy deck statistics for a format."""

    expansion: str
    format: str
    total_trophy_decks: int = 0
    analyzed_decks: int = 0
    archetype_stats: dict[str, ArchetypeTrophyStats] = field(default_factory=dict)
    overall_card_usage: Counter = field(default_factory=Counter)
    # Overall CMC stats
    overall_cmc_stats: Optional[CMCStats] = None
    # Overall splash stats
    overall_splash_stats: Optional[SplashStats] = None

    def get_archetype_ranking(self) -> list[ArchetypeTrophyStats]:
        """Get archetypes ranked by trophy count."""
        return sorted(
            self.archetype_stats.values(),
            key=lambda x: x.trophy_count,
            reverse=True,
        )

    def get_top_cards_overall(self, n: int = 20) -> list[tuple[str, int]]:
        """Get top N most-used cards across all trophy decks."""
        return self.overall_card_usage.most_common(n)

    def get_archetype_share(self, colors: str) -> float:
        """Get trophy share for an archetype."""
        if self.analyzed_decks == 0:
            return 0.0
        stats = self.archetype_stats.get(colors)
        if not stats:
            return 0.0
        return stats.trophy_count / self.analyzed_decks

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        # Filter out basic lands from overall card usage
        basic_lands = {"Plains", "Island", "Swamp", "Mountain", "Forest"}
        filtered_card_usage = {
            k: v for k, v in self.overall_card_usage.items()
            if k not in basic_lands
        }

        # Build archetype ranking with new stats
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
                # CMC stats
                "avg_cmc": round(arch.avg_cmc, 2) if arch.deck_cmcs else None,
                # Splash stats
                "splash_count": arch.splash_count,
                "splash_rate_pct": round(arch.splash_rate * 100, 1),
                "splash_colors": dict(arch.splash_colors.most_common()) if arch.splash_colors else {},
                # Top cards (filter basic lands)
                "top_cards": [
                    {
                        "name": name,
                        "count": count,
                        "per_deck_avg": round(count / arch.trophy_count, 2) if arch.trophy_count else 0,
                    }
                    for name, count in arch.card_usage.most_common(20)
                    if name not in basic_lands
                ][:20],
            }
            archetype_ranking.append(arch_data)

        return {
            "meta": {
                "expansion": self.expansion,
                "format": self.format,
                "analyzed_at": __import__("datetime").datetime.now().isoformat(),
                "total_trophy_decks": self.total_trophy_decks,
                "analyzed_decks": self.analyzed_decks,
            },
            "overall_cmc_stats": self.overall_cmc_stats.to_dict() if self.overall_cmc_stats else None,
            "overall_splash_stats": self.overall_splash_stats.to_dict() if self.overall_splash_stats else None,
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
    """Analyzes trophy deck data from 17lands."""

    def __init__(
        self,
        loader: Optional[SeventeenLandsLoader] = None,
        max_decks: int = 100,
        delay_between_requests: float = 0.3,
    ):
        """
        Initialize trophy analyzer.

        Args:
            loader: 17lands data loader
            max_decks: Maximum number of decks to analyze (for rate limiting)
            delay_between_requests: Delay between deck detail requests
        """
        self.loader = loader or SeventeenLandsLoader()
        self.max_decks = max_decks
        self.delay = delay_between_requests

    def analyze(
        self,
        expansion: str,
        format: str = "PremierDraft",
        fetch_details: bool = True,
    ) -> TrophyStats:
        """
        Analyze trophy decks for a format.

        Args:
            expansion: Set code
            format: Draft format
            fetch_details: Whether to fetch full deck lists (slower but more detailed)

        Returns:
            TrophyStats with analysis results
        """
        stats = TrophyStats(expansion=expansion, format=format)

        # Fetch trophy deck list
        trophy_list = self.loader.fetch_trophy_decks(expansion, format)
        stats.total_trophy_decks = len(trophy_list)

        if not trophy_list:
            logger.warning(f"No trophy decks found for {expansion} {format}")
            return stats

        logger.info(f"Analyzing {min(len(trophy_list), self.max_decks)} of {len(trophy_list)} trophy decks")

        # Analyze decks
        decks_to_analyze = trophy_list[: self.max_decks]
        archetype_decks: dict[str, list[TrophyDeck]] = defaultdict(list)

        # Track overall CMC and splash stats
        all_deck_cmcs: list[float] = []
        overall_splash = SplashStats()

        for i, trophy_data in enumerate(decks_to_analyze):
            deck_details = None

            if fetch_details:
                # Rate limiting
                if i > 0:
                    time.sleep(self.delay)

                deck_details = self.loader.fetch_deck_details(
                    trophy_data.get("aggregate_id", ""),
                    trophy_data.get("deck_index", 0),
                )

            deck = TrophyDeck.from_api_data(trophy_data, deck_details)
            archetype_decks[deck.colors].append(deck)

            # Track overall card usage
            for card_name in deck.maindeck_card_names:
                stats.overall_card_usage[card_name] += 1

            # Track CMC (only if we have CMC data)
            if deck.maindeck_card_cmcs:
                deck_avg_cmc = deck.avg_cmc
                if deck_avg_cmc > 0:
                    all_deck_cmcs.append(deck_avg_cmc)

            # Track splash stats (only if we have color data)
            if deck.maindeck_card_colors:
                overall_splash.total_decks += 1
                if deck.is_splash:
                    overall_splash.splash_decks += 1
                    for color in deck.splash_colors:
                        overall_splash.splash_by_color[color] += 1

                total_colors = deck.total_colors
                if total_colors == 3:
                    overall_splash.three_color_decks += 1
                elif total_colors >= 4:
                    overall_splash.four_plus_color_decks += 1

            if (i + 1) % 20 == 0:
                logger.info(f"Analyzed {i + 1}/{len(decks_to_analyze)} trophy decks")

        stats.analyzed_decks = len(decks_to_analyze)

        # Build overall CMC stats
        if all_deck_cmcs:
            cmc_distribution = {"1": 0, "2": 0, "3": 0, "4": 0, "5": 0, "6+": 0}
            for cmc in all_deck_cmcs:
                if cmc < 1.5:
                    cmc_distribution["1"] += 1
                elif cmc < 2.5:
                    cmc_distribution["2"] += 1
                elif cmc < 3.5:
                    cmc_distribution["3"] += 1
                elif cmc < 4.5:
                    cmc_distribution["4"] += 1
                elif cmc < 5.5:
                    cmc_distribution["5"] += 1
                else:
                    cmc_distribution["6+"] += 1

            stats.overall_cmc_stats = CMCStats(
                avg_cmc=sum(all_deck_cmcs) / len(all_deck_cmcs),
                min_cmc=min(all_deck_cmcs),
                max_cmc=max(all_deck_cmcs),
                cmc_distribution=cmc_distribution,
            )

        # Set overall splash stats
        if overall_splash.total_decks > 0:
            stats.overall_splash_stats = overall_splash

        # Build archetype stats
        for colors, decks in archetype_decks.items():
            arch_stats = ArchetypeTrophyStats(
                colors=colors,
                guild_name=get_guild_name(colors),
                trophy_count=len(decks),
            )

            for deck in decks:
                arch_stats.total_wins += deck.wins
                arch_stats.total_losses += deck.losses
                for card_name in deck.maindeck_card_names:
                    arch_stats.card_usage[card_name] += 1

                # Track CMC per archetype
                if deck.maindeck_card_cmcs and deck.avg_cmc > 0:
                    arch_stats.deck_cmcs.append(deck.avg_cmc)

                # Track splash per archetype
                if deck.maindeck_card_colors and deck.is_splash:
                    arch_stats.splash_count += 1
                    for color in deck.splash_colors:
                        arch_stats.splash_colors[color] += 1

            stats.archetype_stats[colors] = arch_stats

        logger.info(
            f"Trophy analysis complete: {stats.analyzed_decks} decks, "
            f"{len(stats.archetype_stats)} archetypes"
        )

        return stats


def analyze_trophy_decks(
    expansion: str,
    format: str = "PremierDraft",
    max_decks: int = 100,
    fetch_details: bool = True,
) -> TrophyStats:
    """
    Convenience function to analyze trophy decks.

    Args:
        expansion: Set code
        format: Draft format
        max_decks: Maximum decks to analyze
        fetch_details: Whether to fetch full deck lists

    Returns:
        TrophyStats with analysis results
    """
    analyzer = TrophyAnalyzer(max_decks=max_decks)
    return analyzer.analyze(expansion, format, fetch_details)
