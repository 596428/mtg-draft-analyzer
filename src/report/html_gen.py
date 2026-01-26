"""HTML draft guide report generation."""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

from src.models.archetype import Archetype, ColorStrength, GUILD_NAMES
from src.models.card import Card, Rarity
from src.models.meta import MetaSnapshot

logger = logging.getLogger(__name__)


def simple_markdown_to_html(text: str) -> str:
    """Convert simple markdown to HTML for LLM analysis display."""
    if not text:
        return ""

    # Escape HTML entities first
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Convert headers (### -> h4, ## -> h3)
    text = re.sub(r"^### (.+)$", r"<h4>\1</h4>", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.+)$", r"<h3>\1</h3>", text, flags=re.MULTILINE)

    # Convert bold (**text**)
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)

    # Convert bullet points (- item)
    lines = text.split("\n")
    result = []
    in_list = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            if not in_list:
                result.append("<ul>")
                in_list = True
            result.append(f"<li>{stripped[2:]}</li>")
        else:
            if in_list:
                result.append("</ul>")
                in_list = False
            # Convert paragraphs (empty lines become paragraph breaks)
            if stripped == "":
                result.append("<br>")
            elif not stripped.startswith("<h"):
                result.append(f"<p>{stripped}</p>" if stripped else "")
            else:
                result.append(stripped)

    if in_list:
        result.append("</ul>")

    return "\n".join(result)


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

        # Add custom filters (handle None values gracefully)
        self.env.filters["format_number"] = lambda n: f"{n:,}" if n is not None else "N/A"
        self.env.filters["percent"] = lambda n: f"{n * 100:.1f}%" if n is not None else "N/A"
        self.env.filters["percent2"] = lambda n: f"{n * 100:.2f}%" if n is not None else "N/A"
        self.env.filters["grade_class"] = self._grade_to_class
        self.env.filters["markdown"] = lambda text: Markup(simple_markdown_to_html(text)) if text else ""

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
                # Pass all cards, template filters by rarity (10 per group)
                "top_cards": arch_cards,
            })

        # Build sets for card badges
        top_common_names = set()
        top_uncommon_names = set()
        bomb_names = set()

        # Collect top commons/uncommons from color analysis
        for color in snapshot.top_colors:
            if color.top_commons:
                top_common_names.update(color.top_commons[:3])
            if color.top_uncommons:
                top_uncommon_names.update(color.top_uncommons[:3])

        # Collect bombs from archetypes and high-grade cards
        for arch in snapshot.top_archetypes:
            if arch.bombs:
                bomb_names.update(arch.bombs[:5])

        # Also add S and A+ grade cards as bombs
        for card in all_cards_sorted:
            if card.grade in ("S", "A+"):
                bomb_names.add(card.name)

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

            # Card badge sets
            "top_common_names": top_common_names,
            "top_uncommon_names": top_uncommon_names,
            "bomb_names": bomb_names,

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
            "llm_format_overview": snapshot.llm_format_overview if include_llm else None,
        }

        return template.render(**context)

    def _get_archetype_cards(
        self,
        snapshot: MetaSnapshot,
        archetype: Archetype,
    ) -> list[Card]:
        """Get top performing cards for a specific archetype.

        Only includes cards that have viability data for this archetype
        (i.e., archetype_wrs contains this archetype's colors).
        Cards are sorted by composite_score (descending).
        """
        # Find cards that have viability data for this specific archetype
        matching_cards = []
        for card in snapshot.all_cards:
            # Only include cards that have data for this archetype
            if archetype.colors in card.stats.archetype_wrs:
                matching_cards.append(card)

        # Sort by composite_score (descending)
        matching_cards.sort(key=lambda c: c.composite_score, reverse=True)

        return matching_cards

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
