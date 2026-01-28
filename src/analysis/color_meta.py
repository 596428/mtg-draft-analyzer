"""Color and meta analysis orchestration."""

import logging
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from src.data.cache import CacheManager
from src.data.loader import SeventeenLandsLoader
from src.data.scryfall import ScryfallClient
from src.llm.gemini_client import GeminiClient
from src.models.card import Card
from src.models.meta import FormatSpeed, MetaSnapshot, SplashIndicator, ThresholdConfig
from src.scoring.calibration import Calibrator
from src.scoring.card_scorer import CardScorer
from src.scoring.color_scorer import ColorScorer
from src.scoring.irregularity import (
    IrregularityDetector,
    enrich_cards_with_variance,
)
from src.analysis.trophy_analyzer import TrophyAnalyzer, TrophyStats

logger = logging.getLogger(__name__)


def is_mana_fixer(card: Card) -> bool:
    """Detect if a card is a mana fixer.

    Includes: dual lands, treasure producers, mana dorks, etc.
    Excludes: basic lands
    """
    oracle_text = (card.oracle_text or "").lower()
    type_line = (card.type_line or "").lower()

    # Basic land exclusion
    basic_names = ["plains", "island", "swamp", "mountain", "forest"]
    if any(basic in card.name.lower() for basic in basic_names):
        return False

    # Land check - dual lands / tap lands
    if "land" in type_line:
        # Dual lands typically produce multiple colors
        if "add {" in oracle_text or "any color" in oracle_text:
            return True
        # Tap lands with two mana types
        mana_symbols = ["{W}", "{U}", "{B}", "{R}", "{G}"]
        mana_count = sum(1 for symbol in mana_symbols if symbol.lower() in oracle_text)
        if mana_count >= 2:
            return True
        return False

    # Mana-producing effects
    mana_keywords = [
        "add {",
        "add one mana",
        "treasure",
        "any color",
        "mana of any",
        "add mana of any",
    ]
    return any(kw in oracle_text for kw in mana_keywords)


def is_dual_land(card: Card) -> bool:
    """Detect if a card is a dual land (produces 2+ colors).

    Includes: Tap lands, shock lands, fast lands, check lands, pain lands,
    pathways, triomes, campuses, etc.

    Uses multiple detection methods:
    1. Oracle text contains 2+ different mana symbols
    2. Oracle text says "mana of any color"
    3. Card name matches known dual land patterns
    """
    type_line = (card.type_line or "").lower()
    oracle_text = (card.oracle_text or "").lower()
    name_lower = card.name.lower()

    if "land" not in type_line:
        return False

    # Basic land exclusion
    basic_names = ["plains", "island", "swamp", "mountain", "forest"]
    if any(name_lower == basic for basic in basic_names):
        return False

    # Method 1: Oracle text contains 2+ different mana symbols
    mana_symbols = ["{w}", "{u}", "{b}", "{r}", "{g}"]
    produces_count = sum(1 for s in mana_symbols if s in oracle_text)
    if produces_count >= 2:
        return True

    # Method 2: Produces "any color" mana
    any_color_phrases = [
        "mana of any color",
        "mana of any type",
        "one mana of any color",
        "add one mana of any",
    ]
    if any(phrase in oracle_text for phrase in any_color_phrases):
        return True

    # Method 3: Card name matches known dual land patterns
    dual_patterns = [
        "temple",      # Temple of X (scry lands)
        "pathway",     # Modal DFCs
        "campus",      # Strixhaven campuses
        "triome",      # Triomes
        "bridge",      # Artifact lands dual
        "falls",       # Hinterland Harbor style
        "harbor",
        "grove",
        "clearing",
        "fortress",
        "manor",
        "tunnel",
        "channel",
        "gardens",     # Botanical Sanctum style
        "sanctum",
        "copse",
        "concealed courtyard",  # Fast lands
        "inspiring vantage",
        "spire of industry",
    ]
    if any(p in name_lower for p in dual_patterns):
        return True

    # Method 4: Type line indicates dual land
    dual_type_patterns = ["gate", "locus"]
    if any(p in type_line for p in dual_type_patterns):
        return True

    return False


def is_card_playable_in_colors(card: Card, deck_colors: set[str]) -> bool:
    """Check if a card can be cast with the given deck colors.

    For hybrid cards: checks if deck_colors can satisfy all hybrid symbols.
    For gold cards: checks if all card colors are in deck_colors.

    Args:
        card: Card object with hybrid data populated
        deck_colors: Set of colors available in the deck (e.g., {"W", "U"})

    Returns:
        True if the card can be cast with deck_colors, False otherwise

    Examples:
        {W/R} card with deck_colors={"W"} → True (W can pay for W/R)
        {W/R} card with deck_colors={"U"} → False (U cannot pay for W/R)
        {W}{R} card with deck_colors={"W"} → False (needs both W and R)
        {W}{R} card with deck_colors={"W","R"} → True
    """
    if not deck_colors:
        return False

    if card.is_hybrid and card.hybrid_color_options:
        # Hybrid card: each hybrid symbol must be payable by at least one deck color
        for hybrid_opts in card.hybrid_color_options:
            if not (hybrid_opts & deck_colors):
                # No deck color can pay for this hybrid symbol
                return False

        # Also check required (non-hybrid) colors
        if card.min_colors_required:
            # min_colors_required already accounts for optimal hybrid choices
            # But we need to verify the required_colors (non-hybrid) are covered
            # Since min_colors is computed optimally, we just check subset
            # Actually, we should check that required non-hybrid colors are in deck
            # min_colors_required is the minimum set needed, so if deck has those, it works
            pass

        return True
    else:
        # Non-hybrid card: all card colors must be in deck
        card_colors = set(card.colors) if card.colors else set()
        if not card_colors:
            # Colorless card: always playable
            return True
        return card_colors <= deck_colors


def requires_splash_for_card(card: Card, base_colors: set[str]) -> bool:
    """Check if a card requires splash colors beyond the base.

    For hybrid cards: returns False if base_colors can cast the card.
    For gold cards: returns True if any card color is outside base_colors.

    Args:
        card: Card object with hybrid data populated
        base_colors: The main colors of the deck (e.g., {"W", "U"} for Azorius)

    Returns:
        True if playing this card requires additional mana sources beyond base_colors

    Examples:
        {U/R} hybrid with base={"W","U"} → False (U covers the hybrid)
        {U}{R} gold with base={"W","U"} → True (R is a splash)
        {W}{U} gold with base={"W","U"} → False (fully covered)
    """
    if not base_colors:
        return True

    if card.is_hybrid and card.hybrid_color_options:
        # Hybrid card: check if base_colors can pay for all hybrid symbols
        for hybrid_opts in card.hybrid_color_options:
            if not (hybrid_opts & base_colors):
                # This hybrid symbol requires a splash
                return True
        return False
    else:
        # Non-hybrid card: check if all colors are in base
        card_colors = set(card.colors) if card.colors else set()
        if not card_colors:
            # Colorless: no splash needed
            return False
        return not card_colors <= base_colors


@dataclass
class KeywordDistribution:
    """Keyword/mechanic distribution by color for LLM context."""

    distribution: dict[str, dict[str, int]] = field(default_factory=dict)
    totals: dict[str, int] = field(default_factory=dict)

    def format_for_llm(self, mechanic_names: list[str] = None) -> str:
        """Format keyword distribution for LLM prompt.

        Args:
            mechanic_names: Optional list of set mechanics to prioritize.
                           If None, shows keywords with 3+ total cards.

        Returns:
            Formatted string like:
            - **Convoke**: W 2장, U 3장, B 0장, R 0장, G 1장 (총 6장)
            - **Flying**: W 5장, U 8장, B 2장, R 1장, G 0장 (총 16장)
        """
        lines = []
        colors = ["W", "U", "B", "R", "G"]

        # Determine which keywords to show
        if mechanic_names:
            keywords_to_show = [
                k for k in self.distribution
                if k.lower() in [m.lower() for m in mechanic_names]
            ]
            # Also include high-frequency keywords not in mechanic_names
            for k, total in self.totals.items():
                if total >= 5 and k not in keywords_to_show:
                    keywords_to_show.append(k)
        else:
            # Show keywords with 3+ total cards
            keywords_to_show = [k for k, t in self.totals.items() if t >= 3]

        for keyword in sorted(keywords_to_show):
            color_dist = self.distribution.get(keyword, {})
            total = self.totals.get(keyword, 0)
            parts = [f"{c} {color_dist.get(c, 0)}장" for c in colors]
            lines.append(f"- **{keyword}**: {', '.join(parts)} (총 {total}장)")

        return "\n".join(lines) if lines else "키워드 분포 데이터 없음"


def aggregate_keyword_distribution(cards: list[Card]) -> KeywordDistribution:
    """Aggregate keyword distribution by color from card list.

    Args:
        cards: List of Card objects with keywords populated from Scryfall

    Returns:
        KeywordDistribution object with per-keyword color counts

    Example output for Convoke:
        distribution["Convoke"] = {"W": 2, "U": 3, "B": 0, "R": 0, "G": 1}
        totals["Convoke"] = 6
    """
    distribution = defaultdict(lambda: defaultdict(int))
    totals = defaultdict(int)

    for card in cards:
        if not card.keywords:
            continue

        # Get card colors (might be multi-color)
        card_colors = list(card.colors) if card.colors else []

        for keyword in card.keywords:
            totals[keyword] += 1
            # Attribute to each color the card has
            for color in card_colors:
                if color in "WUBRG":
                    distribution[keyword][color] += 1
            # For colorless cards, don't add to any color distribution

    return KeywordDistribution(
        distribution={k: dict(v) for k, v in distribution.items()},
        totals=dict(totals),
    )


def _classify_speed_from_api(avg_length: float, wr_on_play: float) -> tuple[str, int]:
    """Classify speed from direct API metrics.

    Args:
        avg_length: Average game length in turns
        wr_on_play: Win rate when going first (0.0-1.0)

    Returns:
        Tuple of (speed_label, score)
    """
    score = 0

    # Game length scoring (historical range: ~6.6-9.9 turns)
    # Lower = faster format
    if avg_length < 8.2:
        score += 2
    elif avg_length < 8.5:
        score += 1
    elif avg_length > 9.2:
        score -= 2
    elif avg_length > 9.0:
        score -= 1

    # Win rate on play scoring (historical range: ~50-54%)
    # Higher = faster format (going first matters more)
    if wr_on_play > 0.530:
        score += 2
    elif wr_on_play > 0.525:
        score += 1
    elif wr_on_play < 0.510:
        score -= 2
    elif wr_on_play < 0.515:
        score -= 1

    # Convert score to label
    if score >= 3:
        label = "초고속"
    elif score >= 1:
        label = "빠름"
    elif score <= -3:
        label = "매우 느림"
    elif score <= -1:
        label = "느림"
    else:
        label = "보통"

    return label, score


def _generate_speed_interpretation(
    avg_length: Optional[float],
    wr_on_play: Optional[float],
    tempo_ratio: float,
    aggro_advantage: float,
) -> str:
    """Generate human-readable interpretation of format speed.

    Explains: 기초 데이터 수준 → 해석 → 결론
    """
    parts = []

    if avg_length is not None and wr_on_play is not None:
        # Part 1: 기초 데이터 수준 (Level of basic data)
        if avg_length < 8.5:
            parts.append(f"평균 게임 길이 {avg_length:.2f}턴은 빠른 편입니다")
        elif avg_length > 9.0:
            parts.append(f"평균 게임 길이 {avg_length:.2f}턴은 느린 편입니다")
        else:
            parts.append(f"평균 게임 길이 {avg_length:.2f}턴은 평균 수준입니다")

        if wr_on_play > 0.525:
            parts.append(f"선공 승률 {wr_on_play:.1%}로 선공 우위가 높습니다")
        elif wr_on_play < 0.515:
            parts.append(f"선공 승률 {wr_on_play:.1%}로 선공 우위가 낮습니다")
        else:
            parts.append(f"선공 승률 {wr_on_play:.1%}로 선/후공 균형이 맞습니다")

        # Part 2: 해석 (Interpretation)
        if avg_length < 8.5 and wr_on_play > 0.525:
            parts.append("→ 템포와 초반 압박이 중요한 빠른 포맷입니다")
        elif avg_length > 9.0 and wr_on_play < 0.515:
            parts.append("→ 카드 밸류와 후반 전략이 중요한 느린 포맷입니다")
        elif avg_length < 8.5 or wr_on_play > 0.52:
            parts.append("→ 빠른 편이지만 균형 잡힌 포맷입니다")
        elif avg_length > 9.0 or wr_on_play < 0.515:
            parts.append("→ 느린 편이지만 다양한 전략이 가능합니다")
        else:
            parts.append("→ 균형 잡힌 포맷으로 다양한 전략이 가능합니다")
    else:
        # Fallback to indirect metrics only
        if tempo_ratio >= 1.02:
            parts.append("템포 비율이 높아 빠른 포맷으로 추정됩니다")
        elif tempo_ratio <= 0.97:
            parts.append("템포 비율이 낮아 느린 포맷으로 추정됩니다")
        else:
            parts.append("템포 비율이 평균 수준입니다")

        if aggro_advantage > 0.02:
            parts.append("저마나 카드가 강세를 보입니다")
        elif aggro_advantage < -0.02:
            parts.append("고마나 카드가 강세를 보입니다")

    return ". ".join(parts) + "."


def calculate_format_speed(
    cards: list[Card],
    play_draw_data: Optional[dict] = None,
) -> FormatSpeed:
    """Calculate format speed indicators.

    Uses direct API metrics (preferred) and indirect card-based metrics.

    Args:
        cards: List of Card objects with stats
        play_draw_data: Optional dict from 17lands play_draw API

    Returns:
        FormatSpeed object with speed analysis
    """
    # Filter cards with sufficient games
    valid_cards = [c for c in cards if c.stats.gih_games >= 200]

    if not valid_cards:
        return FormatSpeed()

    # Calculate OH and GD averages (indirect metrics)
    oh_wrs = [c.stats.oh_wr for c in valid_cards if c.stats.oh_wr is not None and c.stats.oh_wr > 0]
    gd_wrs = [c.stats.gd_wr for c in valid_cards if c.stats.gd_wr is not None and c.stats.gd_wr > 0]

    avg_oh_wr = statistics.mean(oh_wrs) if oh_wrs else 0.5
    avg_gd_wr = statistics.mean(gd_wrs) if gd_wrs else 0.5

    # Tempo ratio
    tempo_ratio = avg_oh_wr / avg_gd_wr if avg_gd_wr > 0 else 1.0

    # CMC-based aggro advantage (only if cards have cmc data from Scryfall)
    # Also filter out cards with gih_wr = 0 or null (data quality issue)
    cards_with_cmc = [
        c for c in valid_cards
        if c.cmc is not None and c.stats.gih_wr is not None and c.stats.gih_wr > 0
    ]

    if cards_with_cmc:
        low_cmc_cards = [c for c in cards_with_cmc if c.cmc <= 2]
        high_cmc_cards = [c for c in cards_with_cmc if c.cmc >= 5]

        low_cmc_wr = (
            statistics.mean(c.stats.gih_wr for c in low_cmc_cards)
            if low_cmc_cards
            else 0.5
        )
        high_cmc_wr = (
            statistics.mean(c.stats.gih_wr for c in high_cmc_cards)
            if high_cmc_cards
            else 0.5
        )
        aggro_advantage = low_cmc_wr - high_cmc_wr
    else:
        # Fallback: no CMC data available (Scryfall enrichment not done)
        low_cmc_wr = 0.5
        high_cmc_wr = 0.5
        aggro_advantage = 0.0
        logger.info("CMC data not available - aggro_advantage calculated as 0")

    # Extract direct API metrics if available
    average_game_length: Optional[float] = None
    win_rate_on_play: Optional[float] = None
    play_draw_sample_size: Optional[int] = None
    turns_distribution: list[int] = []

    if play_draw_data:
        average_game_length = play_draw_data.get("average_game_length")
        win_rate_on_play = play_draw_data.get("win_rate_on_play")
        play_draw_sample_size = play_draw_data.get("sample_size")
        turns_distribution = play_draw_data.get("turns", [])

    # Determine speed label - prioritize direct API metrics if available
    conflicts = []

    if average_game_length is not None and win_rate_on_play is not None:
        # Use direct API metrics (more reliable)
        base_speed, api_score = _classify_speed_from_api(average_game_length, win_rate_on_play)

        # Check for conflicts with indirect metrics
        indirect_fast = tempo_ratio >= 1.02 or aggro_advantage > 0.03
        indirect_slow = tempo_ratio <= 0.97 or aggro_advantage < -0.03

        if api_score >= 1 and indirect_slow:
            conflicts.append("API는 빠름을 나타내지만 간접 지표는 느림을 시사")
        elif api_score <= -1 and indirect_fast:
            conflicts.append("API는 느림을 나타내지만 간접 지표는 빠름을 시사")
    else:
        # Fallback to indirect metrics only
        if tempo_ratio >= 1.03:
            base_speed = "빠름"
        elif tempo_ratio >= 0.99:
            base_speed = "보통"
        elif tempo_ratio >= 0.96:
            base_speed = "약간 느림"
        else:
            base_speed = "느림"

        # Secondary adjustment based on aggro_advantage
        if aggro_advantage > 0.03:
            if base_speed == "보통":
                base_speed = "빠름"
                conflicts.append("CMC 기반 분석: 저마나 카드 강세")
            elif base_speed == "약간 느림":
                base_speed = "보통"
                conflicts.append("CMC 기반 분석이 템포 분석과 상충")
        elif aggro_advantage < -0.03:
            if base_speed == "보통":
                base_speed = "약간 느림"
                conflicts.append("CMC 기반 분석: 고마나 카드 강세")
            elif base_speed == "빠름":
                base_speed = "보통"
                conflicts.append("CMC 기반 분석이 템포 분석과 상충")

    # Check for other conflicts
    if tempo_ratio >= 1.02 and aggro_advantage < -0.02:
        conflicts.append("템포 비율은 빠르지만 고마나 카드가 강함")
    if tempo_ratio < 0.97 and aggro_advantage > 0.02:
        conflicts.append("템포 비율은 느리지만 저마나 카드가 강함")

    # Generate interpretation text
    speed_interpretation = _generate_speed_interpretation(
        average_game_length, win_rate_on_play, tempo_ratio, aggro_advantage
    )

    # Generate recommendation based on speed
    if base_speed in ("초고속", "빠름"):
        recommendation = "템포/어그로 덱 유리, 2드롭 및 커브 중요"
    elif base_speed == "약간 느림":
        recommendation = "약간 느린 포맷, 밸류 중시하되 템포 무시 금지"
    elif base_speed in ("느림", "매우 느림"):
        recommendation = "밸류/컨트롤 덱 유리, 후반 카드와 제거기 중요"
    else:  # 보통
        recommendation = "균형 잡힌 포맷, 다양한 전략 가능"

    return FormatSpeed(
        speed_label=base_speed,
        # Direct API metrics
        average_game_length=average_game_length,
        win_rate_on_play=win_rate_on_play,
        play_draw_sample_size=play_draw_sample_size,
        turns_distribution=turns_distribution,
        speed_interpretation=speed_interpretation,
        # Indirect metrics
        tempo_ratio=tempo_ratio,
        aggro_advantage=aggro_advantage,
        avg_oh_wr=avg_oh_wr,
        avg_gd_wr=avg_gd_wr,
        low_cmc_wr=low_cmc_wr,
        high_cmc_wr=high_cmc_wr,
        conflicts=conflicts,
        recommendation=recommendation,
    )


def calculate_splash_indicator(
    cards: list[Card],
    variants_map: dict[str, list] | None = None,
) -> SplashIndicator:
    """Calculate splash viability indicators.

    Uses:
    - Dual land ALSA and pick rate
    - Mana fixer win rate premium
    - Actual 3-color performance data (if variants_map provided)

    Args:
        cards: All cards in the set
        variants_map: Dict mapping archetype colors to their SplashVariant list
                      e.g., {"WU": [SplashVariant(colors="WUB", ...)], ...}
    """
    # Identify dual lands and mana fixers
    dual_lands = [c for c in cards if is_dual_land(c)]
    mana_fixers = [c for c in cards if is_mana_fixer(c)]

    # Calculate format average WR (filter out gih_wr = 0 or null data quality issues)
    valid_cards = [
        c for c in cards
        if c.stats.gih_games >= 200 and c.stats.gih_wr is not None and c.stats.gih_wr > 0
    ]
    format_avg_wr = (
        statistics.mean(c.stats.gih_wr for c in valid_cards) if valid_cards else 0.5
    )

    # Dual land metrics
    if dual_lands:
        dual_land_alsa = statistics.mean(c.stats.alsa for c in dual_lands)
        dual_land_pick_rate = statistics.mean(c.stats.pick_rate for c in dual_lands)
    else:
        dual_land_alsa = 7.0  # Neutral default
        dual_land_pick_rate = 0.4

    # Mana fixer WR premium (filter out gih_wr = 0 or null)
    if mana_fixers:
        fixer_wrs = [
            c.stats.gih_wr for c in mana_fixers
            if c.stats.gih_games >= 100 and c.stats.gih_wr is not None and c.stats.gih_wr > 0
        ]
        fixer_avg_wr = statistics.mean(fixer_wrs) if fixer_wrs else format_avg_wr
        fixer_wr_premium = fixer_avg_wr - format_avg_wr
    else:
        fixer_wr_premium = 0.0

    # NEW: Validate splash label against actual 3-color performance data
    performance_validation = "데이터 부족"
    positive_splash_count = 0
    negative_splash_count = 0

    if variants_map:
        # Collect all splash variants from all archetypes
        all_variants = [v for vs in variants_map.values() for v in vs]
        if all_variants:
            positive_splash_count = sum(1 for v in all_variants if v.win_rate_delta > 0)
            negative_splash_count = sum(1 for v in all_variants if v.win_rate_delta < 0)

            if positive_splash_count > negative_splash_count * 1.5:
                performance_validation = "양호"
            elif negative_splash_count > positive_splash_count:
                performance_validation = "저조"
            else:
                performance_validation = "보통"

    # Determine splash label based on dual land availability and demand
    # Primary factor: dual_land_count (availability)
    # Secondary factors: ALSA (demand) and pick_rate (competition)
    if len(dual_lands) == 0:
        # No dual lands in set - base on mana fixer availability
        if len(mana_fixers) >= 5 and fixer_wr_premium > 0:
            splash_label = "보통"
            recommendation = "듀얼랜드 없음, 비랜드 마나 픽스로 스플래시 가능"
        else:
            splash_label = "낮음"
            recommendation = "마나 픽스 부족, 2색 집중 권장"
    elif len(dual_lands) >= 10:
        # Many dual lands - check if they're valued
        if dual_land_alsa < 6.0 and dual_land_pick_rate > 0.5:
            splash_label = "높음"
            recommendation = "풍부한 듀얼랜드, 3색 적극 권장"
        elif dual_land_alsa < 7.5:
            splash_label = "높음"
            recommendation = "듀얼랜드 풍부, 스플래시 용이"
        else:
            splash_label = "보통"
            recommendation = "듀얼랜드 있으나 늦게 픽됨, 스플래시 가능"
    elif len(dual_lands) >= 5:
        # Moderate dual land count
        if dual_land_alsa < 5.5 and dual_land_pick_rate > 0.55:
            splash_label = "높음"
            recommendation = "듀얼랜드 경쟁 높음, 조기 픽 권장"
        elif dual_land_alsa > 8.0:
            splash_label = "높음"
            recommendation = "듀얼랜드 늦게 돌아옴, 스플래시 용이"
        else:
            splash_label = "보통"
            recommendation = "폭탄 스플래시 가능, 픽싱 확보 필요"
    else:
        # Few dual lands (1-4)
        if fixer_wr_premium > 0.02:
            splash_label = "보통"
            recommendation = "듀얼랜드 적으나 마나 픽스 강력, 제한적 스플래시"
        else:
            splash_label = "낮음"
            recommendation = "2색 집중 권장, 스플래시 주의"

    # Append performance validation to recommendation if data available
    if performance_validation != "데이터 부족":
        perf_note = f" (실제 3색 성과: {performance_validation}, +{positive_splash_count}/-{negative_splash_count})"
        recommendation += perf_note

    return SplashIndicator(
        splash_label=splash_label,
        dual_land_alsa=dual_land_alsa,
        dual_land_pick_rate=dual_land_pick_rate,
        fixer_wr_premium=fixer_wr_premium,
        dual_land_count=len(dual_lands),
        mana_fixer_count=len(mana_fixers),
        performance_validation=performance_validation,
        positive_splash_count=positive_splash_count,
        negative_splash_count=negative_splash_count,
        recommendation=recommendation,
    )


class ColorMetaAnalyzer:
    """Analyzes color strengths and meta positioning."""

    def __init__(
        self,
        card_scorer: Optional[CardScorer] = None,
        color_scorer: Optional[ColorScorer] = None,
    ):
        self.card_scorer = card_scorer or CardScorer()
        self.color_scorer = color_scorer or ColorScorer()

    def analyze_colors(self, snapshot: MetaSnapshot) -> MetaSnapshot:
        """Add color strength analysis to snapshot."""
        # Get color pair data for archetype success calculation
        from src.models.archetype import ColorPair

        # Calculate color strengths
        snapshot.color_strengths = self.color_scorer.calculate_all_color_strengths(
            snapshot.all_cards,
            color_pairs=[a.color_pair for a in snapshot.archetypes],
        )

        return snapshot


from src.models.archetype import SplashVariant, ColorPair

# ... (imports remain same)

class MetaAnalyzer:
    """Main orchestrator for complete meta analysis."""

    def __init__(
        self,
        loader: Optional[SeventeenLandsLoader] = None,
        scryfall: Optional[ScryfallClient] = None,
        card_scorer: Optional[CardScorer] = None,
        color_scorer: Optional[ColorScorer] = None,
        calibrator: Optional[Calibrator] = None,
        irregularity_detector: Optional[IrregularityDetector] = None,
        gemini_client: Optional[GeminiClient] = None,
        cache: Optional[CacheManager] = None,
    ):
        """
        Initialize meta analyzer.

        Args:
            loader: 17lands data loader
            scryfall: Scryfall client for card text
            card_scorer: Card scoring module
            color_scorer: Color scoring module
            calibrator: Threshold calibrator
            irregularity_detector: Sleeper/trap detector
            gemini_client: LLM client for analysis
            cache: Cache manager
        """
        self.cache = cache or CacheManager()
        self.loader = loader or SeventeenLandsLoader(cache=self.cache)
        self.scryfall = scryfall or ScryfallClient(cache=self.cache)
        self.card_scorer = card_scorer or CardScorer()
        self.color_scorer = color_scorer or ColorScorer()
        self.calibrator = calibrator or Calibrator()
        self.irregularity_detector = irregularity_detector
        self.gemini_client = gemini_client

    def detect_archetype_structure(
        self,
        color_pairs: list[ColorPair],
        min_share_threshold: float = 0.02,  # 2.0% meta share
    ) -> tuple[list[ColorPair], dict[str, list[SplashVariant]]]:
        """
        Dynamically detect main archetypes and splash variants.

        Args:
            color_pairs: All color pair data
            min_share_threshold: Share threshold to be a main archetype

        Returns:
            Tuple of (main_archetypes, variants_map)
            - main_archetypes: List of ColorPair for main archetypes
            - variants_map: Dict mapping main archetype colors to list of variants
        """
        # Filter out any None values that might have slipped through
        color_pairs = [cp for cp in color_pairs if cp is not None]
        
        total_games = sum(cp.games for cp in color_pairs)
        if total_games == 0:
            return [], {}

        main_pairs = []
        candidates = []

        # Step 1: Separate main archetypes and candidates
        for cp in color_pairs:
            share = cp.games / total_games
            
            # Filter extremely low sample size
            if cp.games < 50:
                continue

            if share >= min_share_threshold:
                main_pairs.append(cp)
            elif share >= 0.005:  # 0.5% min for variants
                candidates.append(cp)
        
        # Ensure we have at least some main archetypes
        if not main_pairs:
            # Fallback: take top 5 most played
            sorted_pairs = sorted(color_pairs, key=lambda x: x.games, reverse=True)
            main_pairs = sorted_pairs[:5]

        # Step 2: Map variants to main archetypes
        variants_map = {cp.colors: [] for cp in main_pairs}
        
        # Consider ALL viable pairs (main + candidates) as potential variants for others
        # This allows a 3-color Main Archetype (e.g. WBG) to be a variant of a 2-color Main (e.g. WB)
        all_potential_variants = main_pairs + candidates

        for variant_cand in all_potential_variants:
            cand_colors = set(variant_cand.colors)
            
            for parent in main_pairs:
                if parent == variant_cand:
                    continue

                parent_colors = set(parent.colors)
                
                # Check if candidate is a superset (splash)
                # We strictly look for "Parent + 1 Color" relationship for clean splash recommendations
                if parent_colors.issubset(cand_colors) and len(cand_colors) == len(parent_colors) + 1:
                    
                    added_colors = cand_colors - parent_colors
                    added_color_str = "".join(sorted(list(added_colors)))
                    
                    variant = SplashVariant(
                        colors=variant_cand.colors,
                        added_color=added_color_str,
                        win_rate=variant_cand.win_rate,
                        games=variant_cand.games,
                        meta_share=variant_cand.games / total_games,
                        win_rate_delta=variant_cand.win_rate - parent.win_rate
                    )
                    variants_map[parent.colors].append(variant)

        return main_pairs, variants_map

    def analyze(
        self,
        expansion: str,
        format: str = "PremierDraft",
        include_llm: bool = True,
        include_trophy: bool = True,
        refresh_trophy: bool = False,
        progress_callback: Optional[callable] = None,
    ) -> MetaSnapshot:
        """
        Run complete meta analysis for a set.

        Args:
            expansion: Set code (e.g., "FDN", "DSK")
            format: Draft format (PremierDraft, QuickDraft)
            include_llm: Whether to include LLM analysis
            include_trophy: Whether to include trophy deck analysis (default ON)
            refresh_trophy: Whether to force refresh trophy cache
            progress_callback: Optional callback(step, total, message)

        Returns:
            Complete MetaSnapshot
        """
        # Calculate total steps based on enabled features
        total_steps = 8  # Base steps
        if include_trophy:
            total_steps += 1
        if include_llm:
            total_steps += 1

        def report_progress(step: int, message: str):
            if progress_callback:
                progress_callback(step, total_steps, message)
            logger.info(f"[{step}/{total_steps}] {message}")

        # Step 1: Load card ratings
        report_progress(1, f"Loading card ratings for {expansion} {format}")
        card_stats = self.loader.fetch_card_ratings(expansion, format)

        # Step 2: Load color ratings (with fallback support)
        report_progress(2, "Loading color pair ratings")
        color_pairs = self.loader.fetch_color_ratings(
            expansion, format, card_stats=card_stats
        )

        # New Step: Detect archetype structure
        main_pairs, variants_map = self.detect_archetype_structure(color_pairs)
        logger.info(f"Detected {len(main_pairs)} main archetypes and {sum(len(v) for v in variants_map.values())} variants")

        # Step 3: Calibrate thresholds
        report_progress(3, "Calibrating thresholds from data distribution")
        thresholds = self.calibrator.calibrate(card_stats)

        # Create irregularity detector with calibrated thresholds
        if not self.irregularity_detector:
            self.irregularity_detector = IrregularityDetector.from_thresholds(
                thresholds
            )

        # Step 4: Score all cards
        report_progress(4, "Scoring cards")
        scored_cards = self.card_scorer.score_all_cards(card_stats, thresholds)

        # Step 5: Enrich with Scryfall data (always enabled)
        report_progress(5, "Enriching cards with Scryfall data")
        scored_cards = self._enrich_with_scryfall(scored_cards, expansion)

        # Step 6: Load archetype-specific ratings and calculate variance
        report_progress(6, "Analyzing archetype variance")
        # Fetch ratings only for detected main archetypes
        main_colors = [cp.colors for cp in main_pairs]
        archetype_data = self.loader.fetch_all_archetype_ratings(
            expansion, format, color_pairs=main_colors
        )
        scored_cards = enrich_cards_with_variance(scored_cards, archetype_data)

        # Step 7: Detect irregularities (sleepers/traps)
        report_progress(7, "Detecting sleeper and trap cards")
        scored_cards, sleepers, traps, no_data_cards = self.irregularity_detector.analyze_all_cards(
            scored_cards
        )

        # Step 8: Build archetypes
        report_progress(8, "Building archetype analysis")
        # Build only main archetypes
        archetypes = self.color_scorer.build_all_archetypes(scored_cards, main_pairs)
        
        # Attach variants
        for arch in archetypes:
            if arch.colors in variants_map:
                arch.variants = sorted(
                    variants_map[arch.colors], 
                    key=lambda v: v.win_rate, 
                    reverse=True
                )

        # Calculate format characteristics
        # Fetch play/draw stats for direct speed metrics
        play_draw_data = self.loader.fetch_play_draw_stats(expansion, format)
        format_speed = calculate_format_speed(scored_cards, play_draw_data)
        splash_indicator = calculate_splash_indicator(scored_cards, variants_map)

        # Build snapshot
        snapshot = MetaSnapshot(
            expansion=expansion,
            format=format,
            timestamp=datetime.now(),
            thresholds=thresholds,
            all_cards=scored_cards,
            sleeper_cards=sleepers,
            trap_cards=traps,
            no_data_cards=no_data_cards,
            archetypes=archetypes,
            total_cards=len(scored_cards),
            total_games_analyzed=self.loader.get_total_games(card_stats),
            format_speed=format_speed,
            splash_indicator=splash_indicator,
        )

        # Add color strength analysis
        # For color strength, we still consider all pairs for "Archetype Success" metric?
        # Or just main pairs? Using all_pairs is more accurate for overall color feel.
        snapshot.color_strengths = self.color_scorer.calculate_all_color_strengths(
            scored_cards,
            color_pairs, # Use all pairs for color calculation
        )

        # Dynamic step numbering for optional steps
        current_step = 8

        # Step 9: Trophy deck analysis (optional)
        if include_trophy:
            current_step += 1
            report_progress(current_step, "Analyzing trophy decks")
            snapshot.trophy_stats = self._analyze_trophy_decks(
                expansion, format, refresh_trophy, archetype_ratings=archetype_data
            )

        # Step 10: LLM enrichment (optional)
        if include_llm and self.gemini_client:
            current_step += 1
            report_progress(current_step, "Generating LLM analysis")
            snapshot = self.gemini_client.enrich_snapshot(snapshot)

        logger.info(
            f"Analysis complete: {len(scored_cards)} cards, "
            f"{len(sleepers)} sleepers, {len(traps)} traps"
        )

        return snapshot

    def _analyze_trophy_decks(
        self,
        expansion: str,
        format: str,
        force_refresh: bool = False,
        archetype_ratings: Optional[dict[str, list[dict]]] = None,
    ) -> Optional[TrophyStats]:
        """Analyze trophy decks with caching support (metadata only).

        NOTE: As of January 2025, this no longer fetches individual deck details.
        Trophy analysis uses only metadata from the trophy list endpoint.
        Card usage is populated from archetype_ratings.

        Args:
            expansion: Set code
            format: Draft format
            force_refresh: Whether to ignore cache and fetch fresh data
            archetype_ratings: Optional archetype ratings for card usage data

        Returns:
            TrophyStats or None on failure
        """
        try:
            # Check cache first (unless force refresh)
            if not force_refresh:
                cached = TrophyAnalyzer.load_from_cache(expansion, format)
                if cached:
                    logger.info(f"Using cached trophy analysis for {expansion}")
                    return cached

            # Fetch fresh data (metadata only - no individual deck fetching)
            logger.info(f"Fetching trophy decks for {expansion} (metadata only)")
            analyzer = TrophyAnalyzer(loader=self.loader, max_decks=500)
            stats = analyzer.analyze(expansion, format, archetype_ratings=archetype_ratings)

            # Cache the results
            if stats.analyzed_decks > 0:
                analyzer.save_to_cache(stats)

            return stats

        except Exception as e:
            logger.warning(f"Trophy analysis failed: {e}")
            return None

    def _enrich_with_scryfall(
        self,
        cards: list[Card],
        expansion: str,
    ) -> list[Card]:
        """
        Enrich cards with Scryfall data (oracle_text, cmc, type_line, etc.).

        Args:
            cards: List of Card objects to enrich
            expansion: Set code for Scryfall lookup

        Returns:
            Enriched list of Card objects
        """
        card_names = [c.name for c in cards]
        scryfall_data = self.scryfall.batch_enrich_cards(card_names, expansion)

        enriched_count = 0
        hybrid_count = 0
        for card in cards:
            if card.name in scryfall_data:
                data = scryfall_data[card.name]
                card.oracle_text = data.get("oracle_text")
                card.mana_cost = data.get("mana_cost")
                card.type_line = data.get("type_line")
                card.power = data.get("power")
                card.toughness = data.get("toughness")
                card.keywords = data.get("keywords", [])
                card.cmc = data.get("cmc")
                card.image_uri = data.get("image_uri")
                card.scryfall_uri = data.get("scryfall_uri")
                # Hybrid mana data
                card.is_hybrid = data.get("is_hybrid", False)
                card.min_colors_required = data.get("min_colors_required", set())
                card.hybrid_color_options = data.get("hybrid_color_options", [])
                if card.is_hybrid:
                    hybrid_count += 1
                enriched_count += 1

        logger.info(f"Enriched {enriched_count}/{len(cards)} cards with Scryfall data ({hybrid_count} hybrid cards)")
        return cards

    def quick_analyze(
        self,
        expansion: str,
        format: str = "PremierDraft",
    ) -> MetaSnapshot:
        """
        Run quick analysis without LLM (Scryfall enrichment is always included).

        Args:
            expansion: Set code
            format: Draft format

        Returns:
            MetaSnapshot with basic analysis
        """
        return self.analyze(
            expansion,
            format,
            include_llm=False,
        )
