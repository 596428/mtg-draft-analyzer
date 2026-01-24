"""Color and meta analysis orchestration."""

import logging
import statistics
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


def calculate_format_speed(cards: list[Card]) -> FormatSpeed:
    """Calculate format speed indicators.

    Uses indirect metrics:
    - tempo_ratio: OH WR / GD WR
    - aggro_advantage: low_cmc_wr - high_cmc_wr
    """
    # Filter cards with sufficient games
    valid_cards = [c for c in cards if c.stats.gih_games >= 200]

    if not valid_cards:
        return FormatSpeed()

    # Calculate OH and GD averages
    oh_wrs = [c.stats.oh_wr for c in valid_cards if c.stats.oh_wr > 0]
    gd_wrs = [c.stats.gd_wr for c in valid_cards if c.stats.gd_wr > 0]

    avg_oh_wr = statistics.mean(oh_wrs) if oh_wrs else 0.5
    avg_gd_wr = statistics.mean(gd_wrs) if gd_wrs else 0.5

    # Tempo ratio
    tempo_ratio = avg_oh_wr / avg_gd_wr if avg_gd_wr > 0 else 1.0

    # CMC-based aggro advantage (only if cards have cmc data from Scryfall)
    # Also filter out cards with gih_wr = 0 (data quality issue)
    cards_with_cmc = [
        c for c in valid_cards
        if c.cmc is not None and c.stats.gih_wr > 0
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

    # Determine speed label based on tempo_ratio (primary) and aggro_advantage (secondary)
    # Adjusted thresholds based on real data distribution:
    # Most formats cluster around 0.97-1.01, so thresholds are tightened
    conflicts = []

    if tempo_ratio >= 1.03:
        base_speed = "빠름"
    elif tempo_ratio >= 0.99:
        base_speed = "보통"
    elif tempo_ratio >= 0.96:
        base_speed = "약간 느림"
    else:
        base_speed = "느림"

    # Secondary adjustment based on aggro_advantage
    # Positive = low CMC cards overperform = faster format
    # Negative = high CMC cards overperform = slower format
    if aggro_advantage > 0.03:
        # Strong aggro advantage suggests faster format
        if base_speed == "보통":
            base_speed = "빠름"
            conflicts.append("CMC 기반 분석: 저마나 카드 강세")
        elif base_speed == "약간 느림":
            base_speed = "보통"
            conflicts.append("CMC 기반 분석이 템포 분석과 상충")
    elif aggro_advantage < -0.03:
        # Strong control advantage suggests slower format
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

    # Generate recommendation
    if base_speed == "빠름":
        recommendation = "템포/어그로 덱 유리, 2드롭 및 커브 중요"
    elif base_speed == "약간 느림":
        recommendation = "약간 느린 포맷, 밸류 중시하되 템포 무시 금지"
    elif base_speed == "느림":
        recommendation = "밸류/컨트롤 덱 유리, 후반 카드와 제거기 중요"
    else:  # 보통
        recommendation = "균형 잡힌 포맷, 다양한 전략 가능"

    return FormatSpeed(
        speed_label=base_speed,
        tempo_ratio=tempo_ratio,
        aggro_advantage=aggro_advantage,
        avg_oh_wr=avg_oh_wr,
        avg_gd_wr=avg_gd_wr,
        low_cmc_wr=low_cmc_wr,
        high_cmc_wr=high_cmc_wr,
        conflicts=conflicts,
        recommendation=recommendation,
    )


def calculate_splash_indicator(cards: list[Card]) -> SplashIndicator:
    """Calculate splash viability indicators.

    Uses:
    - Dual land ALSA and pick rate
    - Mana fixer win rate premium
    """
    # Identify dual lands and mana fixers
    dual_lands = [c for c in cards if is_dual_land(c)]
    mana_fixers = [c for c in cards if is_mana_fixer(c)]

    # Calculate format average WR (filter out gih_wr = 0 data quality issues)
    valid_cards = [
        c for c in cards
        if c.stats.gih_games >= 200 and c.stats.gih_wr > 0
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

    # Mana fixer WR premium (filter out gih_wr = 0)
    if mana_fixers:
        fixer_wrs = [
            c.stats.gih_wr for c in mana_fixers
            if c.stats.gih_games >= 100 and c.stats.gih_wr > 0
        ]
        fixer_avg_wr = statistics.mean(fixer_wrs) if fixer_wrs else format_avg_wr
        fixer_wr_premium = fixer_avg_wr - format_avg_wr
    else:
        fixer_wr_premium = 0.0

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

    return SplashIndicator(
        splash_label=splash_label,
        dual_land_alsa=dual_land_alsa,
        dual_land_pick_rate=dual_land_pick_rate,
        fixer_wr_premium=fixer_wr_premium,
        dual_land_count=len(dual_lands),
        mana_fixer_count=len(mana_fixers),
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

    def analyze(
        self,
        expansion: str,
        format: str = "PremierDraft",
        include_llm: bool = True,
        progress_callback: Optional[callable] = None,
    ) -> MetaSnapshot:
        """
        Run complete meta analysis for a set.

        Args:
            expansion: Set code (e.g., "FDN", "DSK")
            format: Draft format (PremierDraft, QuickDraft)
            include_llm: Whether to include LLM analysis
            progress_callback: Optional callback(step, total, message)

        Returns:
            Complete MetaSnapshot
        """
        # Scryfall enrichment is always enabled
        total_steps = 9 if include_llm else 8

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
        archetype_data = self.loader.fetch_all_archetype_ratings(expansion, format)
        scored_cards = enrich_cards_with_variance(scored_cards, archetype_data)

        # Step 7: Detect irregularities (sleepers/traps)
        report_progress(7, "Detecting sleeper and trap cards")
        scored_cards, sleepers, traps = self.irregularity_detector.analyze_all_cards(
            scored_cards
        )

        # Step 8: Build archetypes
        report_progress(8, "Building archetype analysis")
        archetypes = self.color_scorer.build_all_archetypes(scored_cards, color_pairs)

        # Calculate format characteristics
        format_speed = calculate_format_speed(scored_cards)
        splash_indicator = calculate_splash_indicator(scored_cards)

        # Build snapshot
        snapshot = MetaSnapshot(
            expansion=expansion,
            format=format,
            timestamp=datetime.now(),
            thresholds=thresholds,
            all_cards=scored_cards,
            sleeper_cards=sleepers,
            trap_cards=traps,
            archetypes=archetypes,
            total_cards=len(scored_cards),
            total_games_analyzed=self.loader.get_total_games(card_stats),
            format_speed=format_speed,
            splash_indicator=splash_indicator,
        )

        # Add color strength analysis
        snapshot.color_strengths = self.color_scorer.calculate_all_color_strengths(
            scored_cards,
            color_pairs,
        )

        # Step 9: LLM enrichment (optional)
        if include_llm and self.gemini_client:
            report_progress(9, "Generating LLM analysis")
            snapshot = self.gemini_client.enrich_snapshot(snapshot)

        logger.info(
            f"Analysis complete: {len(scored_cards)} cards, "
            f"{len(sleepers)} sleepers, {len(traps)} traps"
        )

        return snapshot

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
                enriched_count += 1

        logger.info(f"Enriched {enriched_count}/{len(cards)} cards with Scryfall data")
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
