"""Scryfall API client for card text and metadata."""

import logging
import time
from typing import Optional

import requests

from src.data.cache import CacheManager

logger = logging.getLogger(__name__)


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
            Dict with oracle_text, mana_cost, type_line, image_uri, scryfall_uri, etc.
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

        return {
            "oracle_text": data.get("oracle_text", ""),
            "mana_cost": data.get("mana_cost", ""),
            "type_line": data.get("type_line", ""),
            "power": data.get("power"),
            "toughness": data.get("toughness"),
            "keywords": data.get("keywords", []),
            "cmc": data.get("cmc", 0),
            "colors": data.get("colors", []),
            "color_identity": data.get("color_identity", []),
            "image_uri": image_uri,
            "scryfall_uri": data.get("scryfall_uri"),
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
