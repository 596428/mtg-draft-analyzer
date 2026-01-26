"""17lands API data loader."""

import logging
from typing import Optional

import requests

from src.data.cache import CacheManager
from src.models.archetype import ColorPair
from src.models.card import CardStats

logger = logging.getLogger(__name__)


def normalize_color_pair(colors: str) -> str:
    """
    Normalize color pair to WUBRG alphabetical order for 17lands API.

    17lands API expects color pairs in WUBRG order (W < U < B < R < G).
    For example: WG not GW, WR not RW, UG not GU.

    Args:
        colors: Two-letter color pair (e.g., "GW", "RW", "GU")

    Returns:
        Normalized color pair in WUBRG order (e.g., "WG", "WR", "UG")
    """
    if len(colors) != 2:
        return colors
    wubrg_order = "WUBRG"
    c1, c2 = colors[0].upper(), colors[1].upper()
    if wubrg_order.index(c1) > wubrg_order.index(c2):
        return c2 + c1
    return colors


class SeventeenLandsLoader:
    """Client for 17lands.com API."""

    BASE_URL = "https://www.17lands.com"
    CARD_RATINGS_ENDPOINT = "/card_ratings/data"
    COLOR_RATINGS_ENDPOINT = "/color_ratings/data"
    PLAY_DRAW_ENDPOINT = "/data/play_draw"

    def __init__(
        self,
        cache: Optional[CacheManager] = None,
        timeout: int = 30,
    ):
        """
        Initialize 17lands loader.

        Args:
            cache: Optional cache manager for caching responses
            timeout: Request timeout in seconds
        """
        self.cache = cache or CacheManager()
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MTG-Draft-Analyzer/0.1.0",
            "Accept": "application/json",
        })

    def _make_request(self, endpoint: str, params: dict) -> list[dict]:
        """Make API request with error handling."""
        url = f"{self.BASE_URL}{endpoint}"

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.error(f"Request timeout for {url}")
            raise
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error {e.response.status_code} for {url}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            raise

    def fetch_card_ratings(
        self,
        expansion: str,
        format: str = "PremierDraft",
        use_cache: bool = True,
    ) -> list[CardStats]:
        """
        Fetch card ratings from 17lands.

        Args:
            expansion: Set code (e.g., "FDN", "DSK", "BLB")
            format: Draft format (PremierDraft, QuickDraft, TradDraft)
            use_cache: Whether to use cached data

        Returns:
            List of CardStats objects
        """
        cache_key = ("card_ratings", expansion, format)

        # Check cache first
        if use_cache:
            cached = self.cache.get(*cache_key)
            if cached:
                logger.info(f"Using cached card ratings for {expansion} {format}")
                return [CardStats.from_17lands(d) for d in cached]

        # Fetch from API
        logger.info(f"Fetching card ratings for {expansion} {format}")
        params = {
            "expansion": expansion,
            "format": format,
        }

        raw_data = self._make_request(self.CARD_RATINGS_ENDPOINT, params)

        # Cache the raw response
        if use_cache:
            self.cache.set(raw_data, *cache_key)

        # Parse and return
        cards = [CardStats.from_17lands(d) for d in raw_data]
        logger.info(f"Loaded {len(cards)} cards for {expansion} {format}")

        return cards

    def fetch_color_ratings(
        self,
        expansion: str,
        format: str = "PremierDraft",
        use_cache: bool = True,
        card_stats: Optional[list[CardStats]] = None,
    ) -> list[ColorPair]:
        """
        Fetch color/archetype ratings from 17lands.

        If the API fails (e.g., 400 error for some sets like OTJ),
        falls back to computing archetype win rates from card data.

        Args:
            expansion: Set code (e.g., "FDN", "DSK", "BLB")
            format: Draft format (PremierDraft, QuickDraft, TradDraft)
            use_cache: Whether to use cached data
            card_stats: Optional card stats for fallback computation

        Returns:
            List of ColorPair objects
        """
        cache_key = ("color_ratings", expansion, format)

        # Check cache first
        if use_cache:
            cached = self.cache.get(*cache_key)
            if cached:
                logger.info(f"Using cached color ratings for {expansion} {format}")
                return [ColorPair.from_17lands(d) for d in cached]

        # Fetch from API
        logger.info(f"Fetching color ratings for {expansion} {format}")
        params = {
            "expansion": expansion,
            "format": format,
        }

        try:
            raw_data = self._make_request(self.COLOR_RATINGS_ENDPOINT, params)

            # Cache the raw response
            if use_cache:
                self.cache.set(raw_data, *cache_key)

            # Parse and return
            colors = [ColorPair.from_17lands(d) for d in raw_data]
            logger.info(f"Loaded {len(colors)} color pairs for {expansion} {format}")

            return colors

        except requests.exceptions.HTTPError as e:
            logger.warning(
                f"Color ratings API unavailable for {expansion} {format}: {e}"
            )

            # Fallback: compute from card data
            if card_stats:
                from src.data.color_fallback import compute_color_pairs_from_cards

                logger.info("Attempting fallback computation from card data...")
                fallback = compute_color_pairs_from_cards(card_stats)
                if fallback:
                    logger.info(
                        f"Computed {len(fallback)} color pairs from card data (fallback)"
                    )
                    return fallback

            logger.warning(
                "No card_stats provided for fallback. "
                "Color pair stats will be empty."
            )
            return []

    def fetch_card_ratings_by_archetype(
        self,
        expansion: str,
        format: str = "PremierDraft",
        colors: str = "",
        use_cache: bool = True,
    ) -> list[dict]:
        """
        Fetch card ratings filtered by color pair.

        Args:
            expansion: Set code
            format: Draft format
            colors: Color pair filter (e.g., "WU", "BR")
            use_cache: Whether to use cached data

        Returns:
            List of raw card data dicts for the archetype
        """
        # Use normalized colors for cache key consistency
        normalized_colors = normalize_color_pair(colors)
        cache_key = ("card_ratings_archetype", expansion, format, normalized_colors)

        if use_cache:
            cached = self.cache.get(*cache_key)
            if cached:
                logger.info(f"Using cached archetype ratings for {expansion} {colors}")
                return cached

        normalized_colors = normalize_color_pair(colors)
        logger.info(f"Fetching archetype card ratings for {expansion} {colors} (API: {normalized_colors})")
        params = {
            "expansion": expansion,
            "format": format,
            "colors": normalized_colors,
        }

        raw_data = self._make_request(self.CARD_RATINGS_ENDPOINT, params)

        if use_cache:
            self.cache.set(raw_data, *cache_key)

        return raw_data

    def fetch_all_archetype_ratings(
        self,
        expansion: str,
        format: str = "PremierDraft",
        color_pairs: Optional[list[str]] = None,
    ) -> dict[str, list[dict]]:
        """
        Fetch card ratings for all archetypes.

        Args:
            expansion: Set code
            format: Draft format
            color_pairs: List of color pairs to fetch (defaults to all 10)

        Returns:
            Dict mapping color pair to list of card data
        """
        if color_pairs is None:
            color_pairs = ["WU", "UB", "BR", "RG", "WG", "WB", "UR", "BG", "WR", "UG"]

        results = {}
        for colors in color_pairs:
            results[colors] = self.fetch_card_ratings_by_archetype(
                expansion, format, colors
            )

        return results

    def get_total_games(self, cards: list[CardStats]) -> int:
        """Estimate total games analyzed from card data."""
        if not cards:
            return 0
        # Use max game count as estimate (most-played card)
        return max(c.game_count for c in cards)

    def fetch_play_draw_stats(
        self,
        expansion: str,
        format: str = "PremierDraft",
        use_cache: bool = True,
    ) -> Optional[dict]:
        """
        Fetch play/draw statistics from 17lands.

        This API returns direct format speed indicators:
        - average_game_length: Average game duration in turns
        - win_rate_on_play: Win rate when going first

        Args:
            expansion: Set code (e.g., "FDN", "DSK", "BLB")
            format: Draft format (PremierDraft, QuickDraft, TradDraft)
            use_cache: Whether to use cached data

        Returns:
            Dict with play/draw stats or None if unavailable
        """
        cache_key = ("play_draw", expansion, format)

        if use_cache:
            cached = self.cache.get(*cache_key)
            if cached:
                logger.info(f"Using cached play_draw stats for {expansion} {format}")
                return cached

        try:
            logger.info(f"Fetching play_draw stats for {expansion} {format}")
            # API returns all formats - need to filter
            raw_data = self._make_request(self.PLAY_DRAW_ENDPOINT, {})

            # Handle response format - could be list or dict with 'data' key
            if isinstance(raw_data, dict):
                result = raw_data.get("data", [])
            else:
                result = raw_data

            for entry in result:
                if (
                    entry.get("expansion") == expansion
                    and entry.get("event_type") == format
                ):
                    if use_cache:
                        self.cache.set(entry, *cache_key)
                    logger.info(
                        f"Found play_draw stats: avg_length={entry.get('average_game_length'):.2f}, "
                        f"wr_on_play={entry.get('win_rate_on_play'):.3f}"
                    )
                    return entry

            logger.warning(f"No play_draw data found for {expansion} {format}")
            return None

        except Exception as e:
            logger.warning(f"play_draw API unavailable: {e}")
            return None
