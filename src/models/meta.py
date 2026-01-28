"""Meta snapshot and configuration models."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from src.models.archetype import Archetype, ColorStrength
from src.models.card import Card

if TYPE_CHECKING:
    from src.analysis.trophy_analyzer import TrophyStats


@dataclass
class ThresholdConfig:
    """Calibrated thresholds based on data distribution."""

    # Variance thresholds
    synergy_variance: float = 0.002
    stable_variance: float = 0.001

    # Irregularity z-score thresholds (relaxed from 1.5/-1.5 to catch more sleepers/traps)
    sleeper_z: float = 1.0
    trap_z: float = -1.0

    # Win rate thresholds
    bomb_wr: float = 0.60
    playable_wr: float = 0.50

    # Sample size thresholds (unified with calibration.py)
    min_games: int = 200

    # Percentiles used for calibration
    calibration_percentiles: dict[str, float] = field(
        default_factory=lambda: {
            "synergy": 75,
            "sleeper": 90,
            "trap": 10,
            "bomb": 95,
            "playable": 50,
        }
    )

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "synergy_variance": self.synergy_variance,
            "stable_variance": self.stable_variance,
            "sleeper_z": self.sleeper_z,
            "trap_z": self.trap_z,
            "bomb_wr": self.bomb_wr,
            "playable_wr": self.playable_wr,
            "min_games": self.min_games,
            "calibration_percentiles": self.calibration_percentiles,
        }


@dataclass
class FormatSpeed:
    """Format speed characteristics based on direct API and indirect metrics.

    Direct metrics (from 17lands play_draw API):
    - average_game_length: Avg game duration in turns (lower = faster)
    - win_rate_on_play: Win rate when going first (higher = faster)

    Indirect metrics:
    - tempo_ratio: OH WR / GD WR (>1.02 = fast, <0.98 = slow)
    - aggro_advantage: low_cmc_wr - high_cmc_wr (positive = fast)
    """

    # Speed classification
    speed_label: str = "보통"  # 초고속, 빠름, 보통, 느림, 매우 느림

    # === Direct API metrics (17lands play_draw) ===
    average_game_length: Optional[float] = None
    win_rate_on_play: Optional[float] = None
    play_draw_sample_size: Optional[int] = None
    turns_distribution: list[int] = field(default_factory=list)
    speed_interpretation: str = ""  # Human-readable interpretation

    # === Indirect metrics (derived from card data) ===
    tempo_ratio: float = 1.0  # OH WR / GD WR
    aggro_advantage: float = 0.0  # low_cmc_wr - high_cmc_wr

    # Component data
    avg_oh_wr: float = 0.0
    avg_gd_wr: float = 0.0
    low_cmc_wr: float = 0.0  # CMC <= 2
    high_cmc_wr: float = 0.0  # CMC >= 5

    # Conflicts detected
    conflicts: list[str] = field(default_factory=list)

    # Strategy recommendation
    recommendation: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "speed_label": self.speed_label,
            # Direct API metrics
            "average_game_length": round(self.average_game_length, 2) if self.average_game_length else None,
            "win_rate_on_play": round(self.win_rate_on_play, 4) if self.win_rate_on_play else None,
            "play_draw_sample_size": self.play_draw_sample_size,
            "speed_interpretation": self.speed_interpretation,
            # Indirect metrics
            "tempo_ratio": round(self.tempo_ratio, 4),
            "aggro_advantage": round(self.aggro_advantage, 4),
            "avg_oh_wr": round(self.avg_oh_wr, 4),
            "avg_gd_wr": round(self.avg_gd_wr, 4),
            "low_cmc_wr": round(self.low_cmc_wr, 4),
            "high_cmc_wr": round(self.high_cmc_wr, 4),
            "conflicts": self.conflicts,
            "recommendation": self.recommendation,
        }


@dataclass
class SplashIndicator:
    """Splash viability indicators based on mana fixing quality.

    Uses dual land pick rates and mana fixer performance.
    Now also validates splash label against actual 3-color performance data.
    """

    # Splash classification
    splash_label: str = "보통"  # 높음, 보통, 낮음

    # Dual land metrics
    dual_land_alsa: float = 7.0  # Lower = picked earlier
    dual_land_pick_rate: float = 0.0

    # Mana fixer performance
    fixer_wr_premium: float = 0.0  # Fixer WR - format avg WR

    # Supporting data
    dual_land_count: int = 0
    mana_fixer_count: int = 0

    # NEW: Performance validation against actual 3-color data
    performance_validation: str = ""  # "양호", "저조", "보통", "데이터 부족"
    positive_splash_count: int = 0    # Number of splash variants with positive delta
    negative_splash_count: int = 0    # Number of splash variants with negative delta

    # Strategy recommendation
    recommendation: str = ""

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "splash_label": self.splash_label,
            "dual_land_alsa": round(self.dual_land_alsa, 2),
            "dual_land_pick_rate": round(self.dual_land_pick_rate, 4),
            "fixer_wr_premium": round(self.fixer_wr_premium, 4),
            "dual_land_count": self.dual_land_count,
            "mana_fixer_count": self.mana_fixer_count,
            "performance_validation": self.performance_validation,
            "positive_splash_count": self.positive_splash_count,
            "negative_splash_count": self.negative_splash_count,
            "recommendation": self.recommendation,
        }


@dataclass
class MetaSnapshot:
    """Complete meta analysis snapshot for a set/format combination."""

    # Identification
    expansion: str
    format: str
    timestamp: datetime = field(default_factory=datetime.now)

    # Calibration
    thresholds: ThresholdConfig = field(default_factory=ThresholdConfig)

    # Cards analysis
    all_cards: list[Card] = field(default_factory=list)
    sleeper_cards: list[Card] = field(default_factory=list)
    trap_cards: list[Card] = field(default_factory=list)
    no_data_cards: list[Card] = field(default_factory=list)

    # Color analysis
    color_strengths: list[ColorStrength] = field(default_factory=list)
    archetypes: list[Archetype] = field(default_factory=list)

    # Summary statistics
    total_cards: int = 0
    total_games_analyzed: int = 0

    # Format characteristics
    format_speed: Optional[FormatSpeed] = None
    splash_indicator: Optional[SplashIndicator] = None

    # Trophy deck statistics (optional)
    trophy_stats: Optional["TrophyStats"] = None

    # LLM analysis (optional)
    llm_meta_analysis: Optional[str] = None  # DEPRECATED: use llm_color_strategy
    llm_color_strategy: Optional[str] = None  # 🎨 색상 전략 (5색 분석 + P1P1)
    llm_strategy_tips: Optional[str] = None
    llm_format_overview: Optional[str] = None
    # Parsed sections from format_overview
    llm_format_characteristics: Optional[str] = None  # 📋 포맷 특성
    llm_archetype_deep_dive: Optional[str] = None     # 🏆 상위 아키타입 심층 분석

    @property
    def top_colors(self) -> list[ColorStrength]:
        """Get colors sorted by strength (best first)."""
        return sorted(self.color_strengths, key=lambda c: c.strength_score, reverse=True)

    @property
    def top_archetypes(self) -> list[Archetype]:
        """Get archetypes sorted by win rate (best first)."""
        return sorted(self.archetypes, key=lambda a: a.win_rate, reverse=True)

    @property
    def top_cards(self) -> list[Card]:
        """Get cards sorted by composite score (best first)."""
        return sorted(self.all_cards, key=lambda c: c.composite_score, reverse=True)

    def get_cards_by_color(self, color: str) -> list[Card]:
        """Get all cards containing a specific color."""
        return [c for c in self.all_cards if color in c.colors]

    def get_cards_by_rarity(self, rarity: str) -> list[Card]:
        """Get all cards of a specific rarity."""
        return [c for c in self.all_cards if c.rarity.value == rarity.lower()]

    def _trophy_stats_to_dict(self) -> Optional[dict]:
        """Convert trophy stats to dictionary."""
        if not self.trophy_stats:
            return None

        ts = self.trophy_stats
        archetype_ranking = []
        for arch in ts.get_archetype_ranking()[:10]:
            archetype_ranking.append({
                "colors": arch.colors,
                "guild_name": arch.guild_name,
                "trophy_count": arch.trophy_count,
                "trophy_share": ts.get_archetype_share(arch.colors),
                "avg_win_rate": arch.win_rate,
                "top_cards": [card for card, count in arch.top_cards(5)],
            })

        return {
            "total_trophy_decks": ts.total_trophy_decks,
            "analyzed_decks": ts.analyzed_decks,
            "archetype_ranking": archetype_ranking,
            "top_cards_overall": [card for card, count in ts.get_top_cards_overall(15)],
        }

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "meta": {
                "expansion": self.expansion,
                "format": self.format,
                "timestamp": self.timestamp.isoformat(),
                "total_cards": self.total_cards,
                "total_games_analyzed": self.total_games_analyzed,
            },
            "thresholds": self.thresholds.to_dict(),
            "format_characteristics": {
                "format_speed": self.format_speed.to_dict() if self.format_speed else None,
                "splash_indicator": self.splash_indicator.to_dict() if self.splash_indicator else None,
                "trophy_stats": self._trophy_stats_to_dict() if self.trophy_stats else None,
            },
            "color_rankings": [cs.to_dict() for cs in self.top_colors],
            "archetype_rankings": [a.to_dict() for a in self.top_archetypes[:10]],
            "top_cards": [c.to_dict() for c in self.top_cards[:20]],
            "sleeper_cards": [c.to_dict() for c in self.sleeper_cards[:10]],
            "trap_cards": [c.to_dict() for c in self.trap_cards[:10]],
            "no_data_cards": [c.to_dict() for c in self.no_data_cards],
            "llm_analysis": {
                "color_strategy": self.llm_color_strategy,  # 🎨 색상 전략
                "meta_analysis": self.llm_meta_analysis,  # DEPRECATED
                "strategy_tips": self.llm_strategy_tips,
                "format_overview": self.llm_format_overview,
                "format_characteristics": self.llm_format_characteristics,
                "archetype_deep_dive": self.llm_archetype_deep_dive,
            },
        }

    def summary(self) -> str:
        """Generate a brief text summary."""
        top_color = self.top_colors[0] if self.top_colors else None
        top_arch = self.top_archetypes[0] if self.top_archetypes else None

        lines = [
            f"=== {self.expansion} {self.format} Meta Snapshot ===",
            f"Analyzed: {self.timestamp.strftime('%Y-%m-%d %H:%M')}",
            f"Total Cards: {self.total_cards}",
            f"Total Games: {self.total_games_analyzed:,}",
            "",
        ]

        if top_color:
            lines.append(f"Best Color: {top_color.color} (score: {top_color.strength_score:.1f})")

        if top_arch:
            lines.append(
                f"Best Archetype: {top_arch.guild_name} (WR: {top_arch.win_rate:.2%})"
            )

        if self.sleeper_cards:
            lines.append(f"Top Sleeper: {self.sleeper_cards[0].name}")

        if self.trap_cards:
            lines.append(f"Top Trap: {self.trap_cards[0].name}")

        return "\n".join(lines)

    def __repr__(self) -> str:
        return f"MetaSnapshot({self.expansion} {self.format}, {self.total_cards} cards)"
