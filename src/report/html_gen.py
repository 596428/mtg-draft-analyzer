"""HTML draft guide report generation."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader

from src.models.archetype import Archetype, ColorStrength, GUILD_NAMES
from src.models.card import Card, Rarity
from src.models.meta import MetaSnapshot

logger = logging.getLogger(__name__)


# Color display mapping
COLOR_NAMES = {
    "W": "White",
    "U": "Blue",
    "B": "Black",
    "R": "Red",
    "G": "Green",
}

COLOR_ICONS = {
    "W": "☀️",
    "U": "💧",
    "B": "💀",
    "R": "🔥",
    "G": "🌲",
}


class HtmlReportGenerator:
    """Generates interactive HTML draft guides from MetaSnapshot."""

    def __init__(
        self,
        template_dir: str = "templates",
        template_name: str = "draft_guide.html.j2",
    ):
        """
        Initialize HTML report generator.

        Args:
            template_dir: Directory containing Jinja2 templates
            template_name: Name of HTML template file
        """
        self.template_dir = Path(template_dir)
        self.template_name = template_name

        # Set up Jinja2 environment with HTML autoescape
        if self.template_dir.exists():
            self.env = Environment(
                loader=FileSystemLoader(str(self.template_dir)),
                autoescape=True,
            )
        else:
            self.env = Environment(autoescape=True)

        # Add custom filters
        self.env.filters["format_number"] = lambda n: f"{n:,}"
        self.env.filters["percent"] = lambda n: f"{n * 100:.1f}%"
        self.env.filters["percent2"] = lambda n: f"{n * 100:.2f}%"
        self.env.filters["grade_class"] = self._grade_to_class

    @staticmethod
    def _grade_to_class(grade: str) -> str:
        """Convert letter grade to CSS class name."""
        return grade.replace("+", "plus").replace("-", "minus").lower()

    def _get_template_content(self) -> str:
        """Get template content from file or return default."""
        template_path = self.template_dir / self.template_name

        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        else:
            logger.warning(
                f"Template not found at {template_path}, using default"
            )
            return self._get_default_template()

    def _get_default_template(self) -> str:
        """Return default HTML template (embedded fallback)."""
        # This is a minimal fallback; full template should be in templates/
        return """<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>{{ expansion }} Draft Guide</title>
    <style>
        body { font-family: sans-serif; background: #1a1a2e; color: #eee; }
        h1 { text-align: center; }
    </style>
</head>
<body>
    <h1>{{ expansion }} {{ format }} Draft Guide</h1>
    <p>Template file not found. Please ensure templates/draft_guide.html.j2 exists.</p>
</body>
</html>"""

    def _prepare_cards_by_grade(self, cards: list[Card]) -> dict[str, list[Card]]:
        """Group cards by grade for tier display."""
        grades = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F"]
        result = {g: [] for g in grades}

        for card in cards:
            if card.grade in result:
                result[card.grade].append(card)

        return result

    def _prepare_cards_by_rarity(self, cards: list[Card]) -> dict[str, list[Card]]:
        """Group cards by rarity."""
        result = {
            "mythic": [],
            "rare": [],
            "uncommon": [],
            "common": [],
        }

        for card in cards:
            rarity_key = card.rarity.value.lower()
            if rarity_key in result:
                result[rarity_key].append(card)

        # Sort each group by composite score
        for key in result:
            result[key].sort(key=lambda c: c.composite_score, reverse=True)

        return result

    def _prepare_cards_by_color(self, cards: list[Card]) -> dict[str, list[Card]]:
        """Group cards by color identity."""
        result = {
            "W": [],
            "U": [],
            "B": [],
            "R": [],
            "G": [],
            "multi": [],
            "colorless": [],
        }

        for card in cards:
            colors = card.colors
            if not colors:
                result["colorless"].append(card)
            elif len(colors) > 1:
                result["multi"].append(card)
            elif colors in result:
                result[colors].append(card)

        # Sort each group
        for key in result:
            result[key].sort(key=lambda c: c.composite_score, reverse=True)

        return result

    def generate_html(
        self,
        snapshot: MetaSnapshot,
        include_llm: bool = True,
    ) -> str:
        """
        Generate interactive HTML draft guide from meta snapshot.

        Args:
            snapshot: MetaSnapshot to generate guide from
            include_llm: Whether to include LLM analysis sections

        Returns:
            Complete HTML string
        """
        template = self.env.from_string(self._get_template_content())

        # Prepare card groupings
        all_cards_sorted = sorted(
            snapshot.all_cards,
            key=lambda c: c.composite_score,
            reverse=True
        )

        cards_by_grade = self._prepare_cards_by_grade(all_cards_sorted)
        cards_by_rarity = self._prepare_cards_by_rarity(all_cards_sorted)
        cards_by_color = self._prepare_cards_by_color(all_cards_sorted)

        # Prepare archetype data with additional computed fields
        archetypes_data = []
        for arch in snapshot.top_archetypes:
            arch_cards = self._get_archetype_cards(snapshot, arch)
            archetypes_data.append({
                "archetype": arch,
                "top_cards": arch_cards[:8],
            })

        context = {
            # Meta info
            "expansion": snapshot.expansion,
            "format": snapshot.format,
            "timestamp": snapshot.timestamp.strftime("%Y-%m-%d %H:%M"),
            "total_cards": snapshot.total_cards,
            "total_games": snapshot.total_games_analyzed,

            # Format characteristics
            "format_speed": snapshot.format_speed,
            "splash_indicator": snapshot.splash_indicator,

            # Color analysis
            "color_strengths": snapshot.top_colors,
            "color_names": COLOR_NAMES,
            "color_icons": COLOR_ICONS,

            # Archetype analysis
            "archetypes": snapshot.top_archetypes,
            "archetypes_data": archetypes_data,
            "guild_names": GUILD_NAMES,

            # Card data
            "all_cards": all_cards_sorted,
            "top_cards": all_cards_sorted[:30],
            "cards_by_grade": cards_by_grade,
            "cards_by_rarity": cards_by_rarity,
            "cards_by_color": cards_by_color,

            # Special cards
            "sleepers": snapshot.sleeper_cards[:10],
            "traps": snapshot.trap_cards[:10],

            # Grade display
            "grade_order": ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D", "F"],

            # LLM analysis (optional)
            "llm_analysis": snapshot.llm_meta_analysis if include_llm else None,
            "llm_strategy": snapshot.llm_strategy_tips if include_llm else None,
        }

        return template.render(**context)

    def _get_archetype_cards(
        self,
        snapshot: MetaSnapshot,
        archetype: Archetype,
    ) -> list[Card]:
        """Get top performing cards for a specific archetype."""
        color1 = archetype.colors[0] if len(archetype.colors) > 0 else ""
        color2 = archetype.colors[1] if len(archetype.colors) > 1 else ""

        # Find cards that are in this color pair
        matching_cards = []
        for card in snapshot.all_cards:
            card_colors = set(card.colors)
            arch_colors = {color1, color2}

            # Card should be playable in this archetype
            if card_colors.issubset(arch_colors) or not card_colors:
                # Get archetype-specific win rate if available
                arch_wr = card.stats.archetype_wrs.get(archetype.colors, card.stats.gih_wr)
                matching_cards.append((card, arch_wr))

        # Sort by archetype win rate
        matching_cards.sort(key=lambda x: x[1], reverse=True)

        return [c[0] for c in matching_cards]

    def save_report(
        self,
        snapshot: MetaSnapshot,
        output_dir: str = "output",
        include_llm: bool = True,
    ) -> str:
        """
        Generate and save HTML draft guide to file.

        Args:
            snapshot: MetaSnapshot to generate guide from
            output_dir: Output directory
            include_llm: Whether to include LLM analysis

        Returns:
            Path to saved HTML file
        """
        # Generate content
        content = self.generate_html(snapshot, include_llm)

        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Generate filename
        timestamp = snapshot.timestamp.strftime("%Y-%m-%d")
        filename = f"{snapshot.expansion}_{snapshot.format}_{timestamp}_draft_guide.html"
        filepath = output_path / filename

        # Write file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"HTML guide saved to {filepath}")

        return str(filepath)
