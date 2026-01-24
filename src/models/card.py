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
    deck_wr: float = 0.0  # win_rate from 17lands API

    # Draft metrics
    alsa: float = 7.0  # Average Last Seen At (lower = picked earlier)
    ata: float = 7.0  # Average Taken At

    # Performance metrics (raw win rates)
    gih_wr: float = 0.0  # Games In Hand Win Rate
    gih_games: int = 0
    gih_wins: int = 0
    gns_wr: float = 0.0  # Games Not Seen Win Rate
    oh_wr: float = 0.0  # Opening Hand Win Rate
    oh_games: int = 0
    gd_wr: float = 0.0  # Games Drawn Win Rate
    gd_games: int = 0

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
    def iwd(self) -> float:
        """Improvement When Drawn (GIH WR - GNS WR)."""
        return self.gih_wr - self.gns_wr

    @classmethod
    def from_17lands(cls, data: dict) -> "CardStats":
        """Create CardStats from 17lands API response."""
        # Parse colors - 17lands uses 'color' field
        colors = data.get("color", "") or ""

        # Parse rarity
        rarity_str = data.get("rarity", "common")
        rarity = Rarity.from_string(rarity_str)

        # Calculate wins from games and win rate
        gih_games = data.get("ever_drawn_game_count", 0) or 0
        gih_wr = data.get("ever_drawn_win_rate", 0.0) or 0.0
        gih_wins = int(gih_games * gih_wr)

        oh_games = data.get("opening_hand_game_count", 0) or 0
        gd_games = data.get("drawn_game_count", 0) or 0

        return cls(
            name=data.get("name", "Unknown"),
            colors=colors,
            rarity=rarity,
            seen_count=data.get("seen_count", 0) or 0,
            pick_count=data.get("pick_count", 0) or 0,
            game_count=data.get("game_count", 0) or 0,
            deck_wr=data.get("win_rate", 0.0) or 0.0,
            alsa=data.get("avg_seen", 7.0) or 7.0,
            ata=data.get("avg_pick", 7.0) or 7.0,
            gih_wr=gih_wr,
            gih_games=gih_games,
            gih_wins=gih_wins,
            gns_wr=data.get("never_drawn_win_rate", 0.0) or 0.0,
            oh_wr=data.get("opening_hand_win_rate", 0.0) or 0.0,
            oh_games=oh_games,
            gd_wr=data.get("drawn_win_rate", 0.0) or 0.0,
            gd_games=gd_games,
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

    # Archetype variance analysis
    archetype_variance: float = 0.0
    stability_score: float = 100.0
    is_synergy_dependent: bool = False

    # Irregularity detection
    irregularity_type: str = "normal"  # "sleeper", "trap", or "normal"
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
        return {
            "name": self.name,
            "colors": self.colors,
            "rarity": self.rarity.value,
            "composite_score": round(self.composite_score, 2),
            "grade": self.grade,
            "gih_wr": round(self.stats.gih_wr, 4),
            "adjusted_gih_wr": round(self.adjusted_gih_wr, 4),
            "gih_games": self.stats.gih_games,
            "alsa": round(self.stats.alsa, 2),
            "iwd": round(self.stats.iwd, 4),
            "stability_score": round(self.stability_score, 2),
            "is_synergy_dependent": self.is_synergy_dependent,
            "irregularity_type": self.irregularity_type,
            "irregularity_z": round(self.irregularity_z, 2),
            "oracle_text": self.oracle_text,
            "mana_cost": self.mana_cost,
            "type_line": self.type_line,
            "image_uri": self.image_uri,
            "scryfall_uri": self.scryfall_uri,
        }

    def __repr__(self) -> str:
        return f"Card({self.name}, {self.grade}, score={self.composite_score:.1f})"
