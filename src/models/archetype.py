"""Archetype and color-related data models."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Color(Enum):
    """MTG color identities."""

    WHITE = "W"
    BLUE = "U"
    BLACK = "B"
    RED = "R"
    GREEN = "G"

    @classmethod
    def from_string(cls, value: str) -> Optional["Color"]:
        """Parse single color from string."""
        mapping = {
            "w": cls.WHITE,
            "white": cls.WHITE,
            "u": cls.BLUE,
            "blue": cls.BLUE,
            "b": cls.BLACK,
            "black": cls.BLACK,
            "r": cls.RED,
            "red": cls.RED,
            "g": cls.GREEN,
            "green": cls.GREEN,
        }
        return mapping.get(value.lower())


# Standard two-color pairs in MTG (WUBRG order for API compatibility)
COLOR_PAIRS = [
    "WU",  # Azorius
    "UB",  # Dimir
    "BR",  # Rakdos
    "RG",  # Gruul
    "WG",  # Selesnya (normalized from GW)
    "WB",  # Orzhov
    "UR",  # Izzet
    "BG",  # Golgari
    "WR",  # Boros (normalized from RW)
    "UG",  # Simic (normalized from GU)
]

# Guild names for two-color pairs (WUBRG order for API compatibility)
GUILD_NAMES = {
    "WU": "Azorius",
    "UB": "Dimir",
    "BR": "Rakdos",
    "RG": "Gruul",
    "WG": "Selesnya",  # normalized from GW
    "WB": "Orzhov",
    "UR": "Izzet",
    "BG": "Golgari",
    "WR": "Boros",     # normalized from RW
    "UG": "Simic",     # normalized from GU
}


@dataclass
class ColorPair:
    """Two-color pair statistics from 17lands."""

    colors: str  # e.g., "WU", "BR"
    wins: int = 0
    games: int = 0
    win_rate: float = 0.0
    is_computed: bool = False  # True if computed from card data (fallback)

    @property
    def guild_name(self) -> str:
        """Get guild name for the color pair."""
        return GUILD_NAMES.get(self.colors, self.colors)

    @classmethod
    def from_17lands(cls, data: dict) -> "ColorPair":
        """Create ColorPair from 17lands API response."""
        colors = data.get("color_name", "") or ""
        games = data.get("games", 0) or 0
        wins = data.get("wins", 0) or 0
        win_rate = wins / games if games > 0 else 0.0

        return cls(
            colors=colors,
            wins=wins,
            games=games,
            win_rate=win_rate,
        )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "colors": self.colors,
            "guild_name": self.guild_name,
            "wins": self.wins,
            "games": self.games,
            "win_rate": round(self.win_rate, 4),
            "is_computed": self.is_computed,
        }


@dataclass
class ColorStrength:
    """Computed strength metrics for a single color."""

    color: str  # Single color: W, U, B, R, G
    strength_score: float = 0.0
    rank: int = 0

    # Component scores
    deck_wr_strength: float = 0.0
    archetype_success: float = 0.0
    top_common_avg: float = 0.0
    top_uncommon_avg: float = 0.0
    bomb_factor: float = 0.0
    depth_factor: float = 0.0

    # Supporting data
    playable_count: int = 0
    total_cards: int = 0

    # Top cards by rarity
    top_commons: list[str] = field(default_factory=list)
    top_uncommons: list[str] = field(default_factory=list)
    top_rares: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "color": self.color,
            "strength_score": round(self.strength_score, 2),
            "rank": self.rank,
            "components": {
                "deck_wr_strength": round(self.deck_wr_strength, 2),
                "archetype_success": round(self.archetype_success, 2),
                "top_common_avg": round(self.top_common_avg, 2),
                "top_uncommon_avg": round(self.top_uncommon_avg, 2),
                "bomb_factor": round(self.bomb_factor, 2),
                "depth_factor": round(self.depth_factor, 2),
            },
            "playable_count": self.playable_count,
            "total_cards": self.total_cards,
            "top_commons": self.top_commons[:5],
            "top_uncommons": self.top_uncommons[:3],
            "top_rares": self.top_rares[:3],
        }


@dataclass
class Archetype:
    """Complete archetype analysis for a color pair."""

    color_pair: ColorPair
    strength_score: float = 0.0
    rank: int = 0

    # Key cards
    key_commons: list[str] = field(default_factory=list)
    key_uncommons: list[str] = field(default_factory=list)
    signpost_uncommon: Optional[str] = None  # The archetype's signpost card
    bombs: list[str] = field(default_factory=list)

    # Archetype characteristics
    synergy_cards: list[str] = field(default_factory=list)  # Cards that overperform in this pair
    trap_cards: list[str] = field(default_factory=list)  # Cards that underperform in this pair

    # Meta positioning
    meta_share: float = 0.0  # Percentage of drafts in this archetype
    trending: str = "stable"  # "up", "down", "stable"

    # Synergy metrics
    synergy_lift: float = 0.0  # Average synergy lift across cards
    synergy_std: float = 0.0  # Synergy stability (lower = more consistent)

    @property
    def colors(self) -> str:
        """Color pair string shortcut."""
        return self.color_pair.colors

    @property
    def guild_name(self) -> str:
        """Guild name shortcut."""
        return self.color_pair.guild_name

    @property
    def win_rate(self) -> float:
        """Win rate shortcut."""
        return self.color_pair.win_rate

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "colors": self.colors,
            "guild_name": self.guild_name,
            "win_rate": round(self.win_rate, 4),
            "strength_score": round(self.strength_score, 2),
            "rank": self.rank,
            "key_commons": self.key_commons[:5],
            "key_uncommons": self.key_uncommons[:3],
            "signpost_uncommon": self.signpost_uncommon,
            "bombs": self.bombs[:3],
            "synergy_cards": self.synergy_cards[:5],
            "trap_cards": self.trap_cards[:3],
            "meta_share": round(self.meta_share, 4),
            "trending": self.trending,
            "synergy_lift": round(self.synergy_lift, 4),
            "synergy_std": round(self.synergy_std, 4),
        }

    def __repr__(self) -> str:
        return f"Archetype({self.guild_name}, WR={self.win_rate:.2%}, rank={self.rank})"
