"""Scryfall API client for card text and metadata."""

import logging
import re
import time
from typing import Optional

import requests

from src.data.cache import CacheManager

logger = logging.getLogger(__name__)

# Mana symbol patterns for hybrid detection
HYBRID_PATTERN = re.compile(r'\{([WUBRG2])/([WUBRG])\}', re.IGNORECASE)
SINGLE_COLOR_PATTERN = re.compile(r'\{([WUBRG])\}', re.IGNORECASE)


def parse_mana_requirements(mana_cost: str) -> dict:
    """Parse mana cost to extract actual color requirements.

    Distinguishes between hybrid mana (W OR R needed) and gold mana (W AND R needed).

    Args:
        mana_cost: Mana cost string (e.g., "{3}{W/R}{W/R}" or "{W}{R}")

    Returns:
        Dict with:
            - is_hybrid: bool - Contains hybrid mana symbols
            - required_colors: set[str] - Colors from non-hybrid symbols (must have)
            - hybrid_options: list[set[str]] - Color choices per hybrid symbol
            - min_colors: set[str] - Minimum colors needed to cast the spell

    Examples:
        "{W}{R}" → required={"W","R"}, hybrid_options=[], min={"W","R"}
        "{W/R}{W/R}" → required=set(), hybrid_options=[{"W","R"},{"W","R"}], min={"W"} or {"R"}
        "{W}{W/R}" → required={"W"}, hybrid_options=[{"W","R"}], min={"W"}
        "{3}{W/U}{B/R}" → required=set(), hybrid_options=[{"W","U"},{"B","R"}], min={"W","B"} or similar
    """
    if not mana_cost:
        return {
            "is_hybrid": False,
            "required_colors": set(),
            "hybrid_options": [],
            "min_colors": set(),
        }

    # Remove hybrid symbols from consideration for required colors
    # by temporarily replacing them
    temp_cost = HYBRID_PATTERN.sub('', mana_cost)

    # 1. Extract required colors (non-hybrid single color symbols)
    required_colors = set()
    for match in SINGLE_COLOR_PATTERN.finditer(temp_cost):
        color = match.group(1).upper()
        if color in "WUBRG":
            required_colors.add(color)

    # 2. Extract hybrid options
    hybrid_options = []
    for match in HYBRID_PATTERN.finditer(mana_cost):
        left, right = match.group(1).upper(), match.group(2).upper()
        options = set()
        if left in "WUBRG":
            options.add(left)
        if right in "WUBRG":
            options.add(right)
        if options:
            hybrid_options.append(options)

    is_hybrid = len(hybrid_options) > 0

    # 3. Calculate minimum colors needed
    if not hybrid_options:
        # No hybrid symbols: required_colors is the answer
        min_colors = required_colors.copy()
    else:
        # With hybrid symbols: find minimum color set that satisfies all hybrid requirements
        # Strategy: For each hybrid, we can choose one color. Find the choice that
        # minimizes total colors needed (preferring colors already in required_colors).

        min_colors = required_colors.copy()

        for hybrid_opts in hybrid_options:
            # Check if any existing color in min_colors can cover this hybrid
            if min_colors & hybrid_opts:
                # Already covered by existing colors
                continue
            else:
                # Need to add a color from this hybrid's options
                # Prefer colors that might help with future hybrids
                # Simple heuristic: pick the first available color
                min_colors.add(min(hybrid_opts))

    return {
        "is_hybrid": is_hybrid,
        "required_colors": required_colors,
        "hybrid_options": hybrid_options,
        "min_colors": min_colors,
    }


def has_hybrid_mana(mana_cost: str) -> bool:
    """Quick check for hybrid mana symbol presence."""
    if not mana_cost:
        return False
    return bool(HYBRID_PATTERN.search(mana_cost))


class ScryfallClient:
    """Client for Scryfall API (card text and metadata)."""

    BASE_URL = "https://api.scryfall.com"
    RATE_LIMIT = 0.1  # 10 requests per second -> 100ms between requests

    def __init__(
        self,
        cache: Optional[CacheManager] = None,
        timeout: int = 15,
    ):
        """
        Initialize Scryfall client.

        Args:
            cache: Optional cache manager
            timeout: Request timeout in seconds
        """
        self.cache = cache or CacheManager()
        self.timeout = timeout
        self.last_request_time = 0.0
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "MTG-Draft-Analyzer/0.1.0",
            "Accept": "application/json",
        })

    def _rate_limit(self) -> None:
        """Ensure rate limiting between requests."""
        elapsed = time.time() - self.last_request_time
        if elapsed < self.RATE_LIMIT:
            time.sleep(self.RATE_LIMIT - elapsed)
        self.last_request_time = time.time()

    def _make_request(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make API request with rate limiting."""
        self._rate_limit()
        url = f"{self.BASE_URL}{endpoint}"

        try:
            response = self.session.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.warning(f"Card not found: {params}")
                return {}
            # Handle temporary errors gracefully (503, 429, etc.)
            if e.response.status_code in (503, 429, 500, 502, 504):
                logger.warning(f"Temporary HTTP error {e.response.status_code} for {url}, skipping")
                return {}
            logger.error(f"HTTP error {e.response.status_code} for {url}")
            raise
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            raise

    def get_card_by_name(
        self,
        name: str,
        set_code: Optional[str] = None,
        use_cache: bool = True,
    ) -> Optional[dict]:
        """
        Get card data by exact name.

        Args:
            name: Exact card name
            set_code: Optional set code to narrow search
            use_cache: Whether to use cache

        Returns:
            Card data dict or None if not found
        """
        cache_key = ("scryfall_card", name, set_code or "")

        if use_cache:
            cached = self.cache.get(*cache_key)
            if cached:
                return cached

        params = {"exact": name}
        if set_code:
            params["set"] = set_code.lower()

        data = self._make_request("/cards/named", params)

        if data and use_cache:
            self.cache.set(data, *cache_key)

        return data if data else None

    def search_cards(
        self,
        query: str,
        use_cache: bool = True,
    ) -> list[dict]:
        """
        Search for cards matching query.

        Args:
            query: Scryfall search query (e.g., "set:fdn type:creature")
            use_cache: Whether to use cache

        Returns:
            List of card data dicts
        """
        cache_key = ("scryfall_search", query)

        if use_cache:
            cached = self.cache.get(*cache_key)
            if cached:
                return cached

        all_cards = []
        has_more = True
        page = 1

        while has_more:
            params = {"q": query, "page": page}
            data = self._make_request("/cards/search", params)

            if not data or "data" not in data:
                break

            all_cards.extend(data["data"])
            has_more = data.get("has_more", False)
            page += 1

            # Limit pagination to avoid too many requests
            if page > 10:
                logger.warning(f"Search pagination limit reached for: {query}")
                break

        if all_cards and use_cache:
            self.cache.set(all_cards, *cache_key)

        return all_cards

    def get_set_cards(
        self,
        set_code: str,
        use_cache: bool = True,
    ) -> list[dict]:
        """
        Get all cards from a set.

        Args:
            set_code: Set code (e.g., "fdn", "dsk")
            use_cache: Whether to use cache

        Returns:
            List of card data dicts
        """
        return self.search_cards(f"set:{set_code.lower()}", use_cache)

    def enrich_card_data(self, card_name: str, set_code: str) -> dict:
        """
        Get enriched card data for LLM context.

        Args:
            card_name: Card name
            set_code: Set code

        Returns:
            Dict with oracle_text, mana_cost, type_line, image_uri, scryfall_uri,
            and hybrid mana information.
        """
        data = self.get_card_by_name(card_name, set_code)

        if not data:
            return {}

        # Extract image URI (handle double-faced cards)
        image_uri = None
        if "image_uris" in data:
            image_uri = data["image_uris"].get("normal")
        elif "card_faces" in data and len(data["card_faces"]) > 0:
            # Double-faced card: use front face image
            front_face = data["card_faces"][0]
            if "image_uris" in front_face:
                image_uri = front_face["image_uris"].get("normal")

        # Parse mana requirements for hybrid detection
        mana_cost = data.get("mana_cost", "")
        mana_info = parse_mana_requirements(mana_cost)

        return {
            "oracle_text": data.get("oracle_text", ""),
            "mana_cost": mana_cost,
            "type_line": data.get("type_line", ""),
            "power": data.get("power"),
            "toughness": data.get("toughness"),
            "keywords": data.get("keywords", []),
            "cmc": data.get("cmc", 0),
            "colors": data.get("colors", []),
            "color_identity": data.get("color_identity", []),
            "image_uri": image_uri,
            "scryfall_uri": data.get("scryfall_uri"),
            # Hybrid mana data
            "is_hybrid": mana_info["is_hybrid"],
            "min_colors_required": mana_info["min_colors"],
            "hybrid_color_options": mana_info["hybrid_options"],
        }

    def batch_enrich_cards(
        self,
        card_names: list[str],
        set_code: str,
        progress_callback: Optional[callable] = None,
    ) -> dict[str, dict]:
        """
        Enrich multiple cards with Scryfall data.

        Args:
            card_names: List of card names
            set_code: Set code
            progress_callback: Optional callback(current, total) for progress

        Returns:
            Dict mapping card name to enriched data
        """
        results = {}
        total = len(card_names)

        for i, name in enumerate(card_names):
            enriched = self.enrich_card_data(name, set_code)
            if enriched:
                results[name] = enriched

            if progress_callback:
                progress_callback(i + 1, total)

        return results
