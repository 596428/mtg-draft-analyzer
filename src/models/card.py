"""Card data models for MTG Draft Analyzer."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Rarity(Enum):
    """Card rarity levels."""

    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    MYTHIC = "mythic"

    @classmethod
    def from_string(cls, value: str) -> "Rarity":
        """Parse rarity from string (case-insensitive)."""
        mapping = {
            "c": cls.COMMON,
            "common": cls.COMMON,
            "u": cls.UNCOMMON,
            "uncommon": cls.UNCOMMON,
            "r": cls.RARE,
            "rare": cls.RARE,
            "m": cls.MYTHIC,
            "mythic": cls.MYTHIC,
        }
        return mapping.get(value.lower(), cls.COMMON)


@dataclass
class CardStats:
    """Raw statistics for a card from 17lands."""

    # Identification
    name: str
    colors: str  # e.g., "W", "UB", "WUG"
    rarity: Rarity

    # Sample sizes
    seen_count: int = 0
    pick_count: int = 0
    game_count: int = 0

    # Deck-level win rate (when card is in pool)
    # None = no data (e.g., Special Guest cards with hidden stats)
    deck_wr: Optional[float] = None  # win_rate from 17lands API

    # Draft metrics
    alsa: float = 7.0  # Average Last Seen At (lower = picked earlier)
    ata: float = 7.0  # Average Taken At

    # Performance metrics (raw win rates)
    # None = no data available (not the same as 0% win rate)
    gih_wr: Optional[float] = None  # Games In Hand Win Rate
    gih_games: int = 0
    gih_wins: int = 0
    gns_wr: Optional[float] = None  # Games Not Seen Win Rate
    oh_wr: Optional[float] = None  # Opening Hand Win Rate
    oh_games: int = 0
    gd_wr: Optional[float] = None  # Games Drawn Win Rate
    gd_games: int = 0

    # Flag indicating whether win rate data is available
    has_valid_wr: bool = False

    # Archetype-specific data (color pair -> win rate)
    archetype_wrs: dict[str, float] = field(default_factory=dict)
    archetype_games: dict[str, int] = field(default_factory=dict)

    @property
    def pick_rate(self) -> float:
        """Calculate pick rate (picks / times seen)."""
        if self.seen_count == 0:
            return 0.0
        return self.pick_count / self.seen_count

    @property
    def iwd(self) -> Optional[float]:
        """Improvement When Drawn (GIH WR - GNS WR)."""
        if self.gih_wr is None or self.gns_wr is None:
            return None
        return self.gih_wr - self.gns_wr

    @classmethod
    def from_17lands(cls, data: dict) -> "CardStats":
        """Create CardStats from 17lands API response.

        Preserves None values for win rates to distinguish between
        "no data" (None) and "0% win rate" (0.0).
        """
        # Parse colors - 17lands uses 'color' field
        colors = data.get("color", "") or ""

        # Parse rarity
        rarity_str = data.get("rarity", "common")
        rarity = Rarity.from_string(rarity_str)

        # Get win rate data - preserve None for missing data
        gih_wr_raw = data.get("ever_drawn_win_rate")
        gns_wr_raw = data.get("never_drawn_win_rate")
        oh_wr_raw = data.get("opening_hand_win_rate")
        gd_wr_raw = data.get("drawn_win_rate")
        deck_wr_raw = data.get("win_rate")

        # Determine if this card has valid win rate data
        has_valid_wr = gih_wr_raw is not None

        # Calculate games (0 if None)
        gih_games = data.get("ever_drawn_game_count", 0) or 0
        oh_games = data.get("opening_hand_game_count", 0) or 0
        gd_games = data.get("drawn_game_count", 0) or 0

        # Calculate wins only if we have valid data
        gih_wins = int(gih_games * gih_wr_raw) if gih_wr_raw is not None else 0

        return cls(
            name=data.get("name", "Unknown"),
            colors=colors,
            rarity=rarity,
            seen_count=data.get("seen_count", 0) or 0,
            pick_count=data.get("pick_count", 0) or 0,
            game_count=data.get("game_count", 0) or 0,
            deck_wr=deck_wr_raw,
            alsa=data.get("avg_seen", 7.0) or 7.0,
            ata=data.get("avg_pick", 7.0) or 7.0,
            gih_wr=gih_wr_raw,
            gih_games=gih_games,
            gih_wins=gih_wins,
            gns_wr=gns_wr_raw,
            oh_wr=oh_wr_raw,
            oh_games=oh_games,
            gd_wr=gd_wr_raw,
            gd_games=gd_games,
            has_valid_wr=has_valid_wr,
        )


@dataclass
class Card:
    """Complete card representation with computed scores."""

    # Core stats
    stats: CardStats

    # Computed scores (filled by scoring modules)
    composite_score: float = 0.0
    grade: str = "C"

    # Bayesian-adjusted metrics
    adjusted_gih_wr: float = 0.0

    # Viability analysis (replaces stability)
    viable_archetypes: int = 0  # Number of archetypes where card performs well
    best_archetype: Optional[str] = None  # Best performing archetype
    off_archetype_penalty: float = 0.0  # WR drop in non-viable archetypes
    natural_premium: Optional[float] = None  # Performance in natural colors vs others

    # Irregularity detection
    irregularity_type: str = "normal"  # "sleeper", "trap", "no_data", or "normal"
    irregularity_z: float = 0.0

    # Scryfall data (optional, for LLM context)
    oracle_text: Optional[str] = None
    mana_cost: Optional[str] = None
    type_line: Optional[str] = None
    power: Optional[str] = None
    toughness: Optional[str] = None
    keywords: list[str] = field(default_factory=list)
    cmc: Optional[float] = None  # Converted mana cost (from Scryfall)
    image_uri: Optional[str] = None  # Card image URL (normal size)
    scryfall_uri: Optional[str] = None  # Scryfall card page link

    @property
    def name(self) -> str:
        """Card name shortcut."""
        return self.stats.name

    @property
    def colors(self) -> str:
        """Card colors shortcut."""
        return self.stats.colors

    @property
    def rarity(self) -> Rarity:
        """Card rarity shortcut."""
        return self.stats.rarity

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        # Handle None values for win rates
        gih_wr = round(self.stats.gih_wr, 4) if self.stats.gih_wr is not None else None
        iwd = round(self.stats.iwd, 4) if self.stats.iwd is not None else None

        return {
            "name": self.name,
            "colors": self.colors,
            "rarity": self.rarity.value,
            "composite_score": round(self.composite_score, 2),
            "grade": self.grade,
            "gih_wr": gih_wr,
            "adjusted_gih_wr": round(self.adjusted_gih_wr, 4),
            "gih_games": self.stats.gih_games,
            "alsa": round(self.stats.alsa, 2),
            "iwd": iwd,
            "has_valid_data": self.stats.has_valid_wr,
            # Viability metrics (replaces stability)
            "viable_archetypes": self.viable_archetypes,
            "best_archetype": self.best_archetype,
            "off_archetype_penalty": round(self.off_archetype_penalty, 4) if self.off_archetype_penalty else 0.0,
            "natural_premium": round(self.natural_premium, 4) if self.natural_premium is not None else None,
            "archetype_wrs": {k: round(v, 4) for k, v in self.stats.archetype_wrs.items()},
            "archetype_games": self.stats.archetype_games,
            # Irregularity
            "irregularity_type": self.irregularity_type,
            "irregularity_z": round(self.irregularity_z, 2),
            # Scryfall data
            "oracle_text": self.oracle_text,
            "mana_cost": self.mana_cost,
            "type_line": self.type_line,
            "image_uri": self.image_uri,
            "scryfall_uri": self.scryfall_uri,
        }

    def __repr__(self) -> str:
        return f"Card({self.name}, {self.grade}, score={self.composite_score:.1f})"
