"""Set metadata loader for mechanic and theme information."""

import logging
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
import yaml

logger = logging.getLogger(__name__)

# Scryfall API constants
SCRYFALL_SEARCH_URL = "https://api.scryfall.com/cards/search"
SCRYFALL_RATE_LIMIT_MS = 100  # 100ms between requests as per Scryfall guidelines


@dataclass
class MechanicWeight:
    """Represents mechanic weight information from Scryfall data."""

    name: str
    card_count: int
    rarities: dict[str, int] = field(default_factory=dict)  # {"common": 10, "uncommon": 5, ...}
    weight: str = "minor"  # "major", "minor", "rare"

    @property
    def weight_label(self) -> str:
        """Get human-readable weight label."""
        if self.weight == "major":
            return "핵심 메커니즘"
        elif self.weight == "rare":
            return "희귀 메커니즘"
        return "보조 메커니즘"

    def __str__(self) -> str:
        """Format for display."""
        rarity_str = ", ".join(f"{r}: {c}" for r, c in self.rarities.items())
        return f"{self.name} ({self.card_count}장, {rarity_str}) - {self.weight_label}"


def _fetch_scryfall_cards(expansion: str) -> list[dict]:
    """
    Fetch all cards from Scryfall for a given expansion.

    Args:
        expansion: Set code (e.g., "ECL", "DSK")

    Returns:
        List of card data dicts
    """
    cards = []
    # Query: set code, exclude basic lands
    query = f"set:{expansion.lower()} -t:basic"
    url = SCRYFALL_SEARCH_URL
    params = {"q": query, "unique": "cards"}

    try:
        while url:
            time.sleep(SCRYFALL_RATE_LIMIT_MS / 1000)  # Rate limiting
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()

            cards.extend(data.get("data", []))

            # Handle pagination
            if data.get("has_more"):
                url = data.get("next_page")
                params = {}  # next_page URL already contains params
            else:
                url = None

        logger.info(f"Fetched {len(cards)} cards from Scryfall for {expansion}")
        return cards

    except requests.exceptions.RequestException as e:
        logger.warning(f"Scryfall API error for {expansion}: {e}")
        return []


def fetch_mechanic_weights(
    expansion: str,
    mechanic_names: list[str],
) -> dict[str, MechanicWeight]:
    """
    Fetch mechanic weight information from Scryfall.

    Analyzes all cards in a set to determine how prevalent each mechanic is.
    This helps prevent LLM over-interpretation of rare mechanics.

    Args:
        expansion: Set code (e.g., "ECL", "DSK")
        mechanic_names: List of mechanic names to search for

    Returns:
        Dict mapping mechanic name to MechanicWeight
    """
    cards = _fetch_scryfall_cards(expansion)
    if not cards:
        return {}

    results = {}

    for mech_name in mechanic_names:
        # Search for mechanic keyword in oracle text or keywords
        mech_lower = mech_name.lower()
        matching_cards = []

        for card in cards:
            # Check keywords field (official keyword abilities)
            keywords = [k.lower() for k in card.get("keywords", [])]
            if mech_lower in keywords:
                matching_cards.append(card)
                continue

            # Check oracle text for mechanic mentions
            oracle = (card.get("oracle_text") or "").lower()
            if mech_lower in oracle:
                matching_cards.append(card)

        if not matching_cards:
            continue

        # Count by rarity
        rarity_counts = Counter(c.get("rarity", "unknown") for c in matching_cards)

        # Determine weight based on card count and rarity distribution
        card_count = len(matching_cards)
        common_uncommon = rarity_counts.get("common", 0) + rarity_counts.get("uncommon", 0)

        if card_count >= 15 and common_uncommon >= 10:
            weight = "major"
        elif card_count <= 5 or common_uncommon == 0:
            weight = "rare"
        else:
            weight = "minor"

        results[mech_name] = MechanicWeight(
            name=mech_name,
            card_count=card_count,
            rarities=dict(rarity_counts),
            weight=weight,
        )

    return results


# Cache for mechanic weights to avoid repeated API calls
_mechanic_weights_cache: dict[str, dict[str, MechanicWeight]] = {}


def get_mechanic_weights(expansion: str, mechanic_names: list[str]) -> dict[str, MechanicWeight]:
    """
    Get mechanic weights for a set (with caching).

    Args:
        expansion: Set code
        mechanic_names: List of mechanic names to analyze

    Returns:
        Dict mapping mechanic name to MechanicWeight
    """
    cache_key = expansion.upper()
    if cache_key not in _mechanic_weights_cache:
        _mechanic_weights_cache[cache_key] = fetch_mechanic_weights(expansion, mechanic_names)
    return _mechanic_weights_cache[cache_key]


@dataclass
class Mechanic:
    """Represents a set mechanic."""

    name: str
    description: str
    strategy_tip: str = ""


@dataclass
class SetMetadata:
    """Metadata for a specific MTG set."""

    code: str
    name: str
    release_date: str = ""
    mechanics: list[Mechanic] = field(default_factory=list)
    themes: list[str] = field(default_factory=list)
    speed_context: str = ""
    draft_tips: list[str] = field(default_factory=list)

    def get_mechanics_summary(
        self,
        mechanic_weights: Optional[dict[str, "MechanicWeight"]] = None,
    ) -> str:
        """
        Generate a formatted summary of set mechanics for LLM prompts.

        Only outputs mechanics information. Other fields (themes, speed_context,
        draft_tips) are intentionally excluded as they either:
        - Duplicate data already calculated from 17lands (speed_context)
        - Should be generated by the LLM, not hardcoded (draft_tips)

        Args:
            mechanic_weights: Optional dict of mechanic weights from Scryfall

        Returns:
            Markdown-formatted string describing set mechanics
        """
        if not self.mechanics:
            return ""

        lines = [f"## {self.name} ({self.code}) 세트 메커닉"]

        # Add guidance for LLM about mechanic weights
        if mechanic_weights:
            lines.append("")
            lines.append("⚠️ **메커니즘별 가중치** (카드 수 기준)")
            lines.append("- 희귀 메커니즘: 과대 해석하지 마세요")
            lines.append("- 핵심 메커니즘: 포맷 정의 요소로 분석 가능")
            lines.append("")

        for mech in self.mechanics:
            # Include weight info if available
            weight_info = ""
            if mechanic_weights and mech.name in mechanic_weights:
                mw = mechanic_weights[mech.name]
                weight_info = f" [{mw.card_count}장, {mw.weight_label}]"
                if mw.weight == "rare":
                    weight_info += " ⚠️희귀"

            lines.append(f"- **{mech.name}**{weight_info}: {mech.description}")
            if mech.strategy_tip:
                lines.append(f"  - 💡 전략: {mech.strategy_tip}")

        # Add hallucination prevention note
        lines.append("")
        lines.append("⚠️ **데이터 기반 분석 원칙**: 위에 명시되지 않은 메커니즘은 언급하지 마세요.")

        return "\n".join(lines)


class SetMetadataLoader:
    """Singleton loader for set metadata configuration."""

    _instance: Optional["SetMetadataLoader"] = None
    _metadata: dict[str, SetMetadata] = {}

    def __new__(cls, config_path: str = "config/set_mechanics.yaml"):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_config(config_path)
        return cls._instance

    def _load_config(self, config_path: str) -> None:
        """Load set metadata from YAML config file."""
        path = Path(config_path)

        if not path.exists():
            logger.warning(f"Set mechanics config not found: {config_path}")
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)

            if not config:
                logger.warning("Empty set mechanics config")
                return

            for code, data in config.items():
                if not isinstance(data, dict):
                    continue

                # Parse mechanics
                mechanics = []
                for mech_data in data.get("mechanics", []):
                    if isinstance(mech_data, dict):
                        mechanics.append(
                            Mechanic(
                                name=mech_data.get("name", ""),
                                description=mech_data.get("description", ""),
                                strategy_tip=mech_data.get("strategy_tip", ""),
                            )
                        )

                self._metadata[code] = SetMetadata(
                    code=code,
                    name=data.get("name", code),
                    release_date=data.get("release_date", ""),
                    mechanics=mechanics,
                    themes=data.get("themes", []),
                    speed_context=data.get("speed_context", ""),
                    draft_tips=data.get("draft_tips", []),
                )

            logger.info(f"Loaded metadata for {len(self._metadata)} sets")

        except yaml.YAMLError as e:
            logger.error(f"Failed to parse set mechanics YAML: {e}")
        except Exception as e:
            logger.error(f"Failed to load set mechanics: {e}")

    def get_set_metadata(self, expansion: str) -> Optional[SetMetadata]:
        """
        Get metadata for a specific set.

        Args:
            expansion: Set code (e.g., "ECL", "DSK")

        Returns:
            SetMetadata if found, None otherwise
        """
        return self._metadata.get(expansion.upper())

    def get_mechanics_summary(
        self,
        expansion: str,
        include_weights: bool = True,
    ) -> str:
        """
        Get formatted mechanics summary for a set.

        Args:
            expansion: Set code
            include_weights: Whether to fetch and include Scryfall mechanic weights

        Returns:
            Formatted string for LLM prompts, empty if set not found
        """
        metadata = self.get_set_metadata(expansion)
        if not metadata:
            return ""

        # Optionally fetch mechanic weights from Scryfall
        mechanic_weights = None
        if include_weights and metadata.mechanics:
            mechanic_names = [m.name for m in metadata.mechanics]
            try:
                mechanic_weights = get_mechanic_weights(expansion, mechanic_names)
            except Exception as e:
                logger.warning(f"Failed to fetch mechanic weights for {expansion}: {e}")

        return metadata.get_mechanics_summary(mechanic_weights)

    def has_metadata(self, expansion: str) -> bool:
        """Check if metadata exists for a set."""
        return expansion.upper() in self._metadata

    @classmethod
    def reset(cls) -> None:
        """Reset singleton instance (mainly for testing)."""
        cls._instance = None
        cls._metadata = {}


# Convenience functions
def get_set_mechanics(expansion: str, include_weights: bool = True) -> str:
    """
    Get set mechanics summary for LLM prompts.

    Args:
        expansion: Set code (e.g., "ECL", "DSK")
        include_weights: Whether to fetch and include Scryfall mechanic weights
                        (helps prevent LLM over-interpretation of rare mechanics)

    Returns:
        Formatted mechanics summary, empty string if not found
    """
    loader = SetMetadataLoader()
    return loader.get_mechanics_summary(expansion, include_weights=include_weights)


def get_set_metadata(expansion: str) -> Optional[SetMetadata]:
    """
    Get full set metadata.

    Args:
        expansion: Set code

    Returns:
        SetMetadata if found, None otherwise
    """
    loader = SetMetadataLoader()
    return loader.get_set_metadata(expansion)


def get_mechanic_names(expansion: str) -> list[str]:
    """
    Get list of mechanic names for a set.

    Args:
        expansion: Set code (e.g., "ECL", "DSK")

    Returns:
        List of mechanic names, empty list if set not found
    """
    metadata = get_set_metadata(expansion)
    if not metadata or not metadata.mechanics:
        return []
    return [m.name for m in metadata.mechanics]
