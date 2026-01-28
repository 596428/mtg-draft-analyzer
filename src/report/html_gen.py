"""HTML draft guide report generation."""

import logging
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

from src.models.archetype import Archetype, ColorStrength, GUILD_NAMES
from src.models.card import Card, Rarity
from src.models.meta import MetaSnapshot

logger = logging.getLogger(__name__)


def simple_markdown_to_html(text: str, card_image_lookup: dict[str, str] | None = None) -> str:
    """Convert simple markdown to HTML for LLM analysis display.

    Args:
        text: Markdown text from LLM
        card_image_lookup: Optional dict mapping card name -> Scryfall image URL
    """
    if not text:
        return ""

    # Escape HTML entities first
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # Convert headers (### -> h4, ## -> h3)
    text = re.sub(r"^### (.+)$", r"<h4>\1</h4>", text, flags=re.MULTILINE)
    text = re.sub(r"^## (.+)$", r"<h3>\1</h3>", text, flags=re.MULTILINE)

    # Convert bold (**text**) with card hover support
    def replace_bold(match: re.Match) -> str:
        content = match.group(1)
        if card_image_lookup and content in card_image_lookup:
            image_url = card_image_lookup[content]
            # HTML escape the image URL
            safe_url = image_url.replace('"', '&quot;')
            return f'<span class="ai-card-hover" data-card-image="{safe_url}"><strong>{content}</strong></span>'
        return f"<strong>{content}</strong>"

    text = re.sub(r"\*\*(.+?)\*\*", replace_bold, text)

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

    # Multi-page configuration: (output_filename, template_name, active_page_key)
    PAGES = [
        ("index.html", "guide_overview.html.j2", "overview"),
        ("archetypes.html", "guide_archetypes.html.j2", "archetypes"),
        ("cards.html", "guide_cards.html.j2", "cards"),
        ("special.html", "guide_special.html.j2", "special"),
    ]

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
        """Group cards by grade for tier display (13 grades)."""
        grades = ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"]
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
        Generate interactive HTML draft guide from meta snapshot (single file).

        Args:
            snapshot: MetaSnapshot to generate guide from
            include_llm: Whether to include LLM analysis sections

        Returns:
            Complete HTML string
        """
        template = self.env.from_string(self._get_template_content())
        context = self._prepare_context(snapshot, include_llm)

        # Extract card_image_lookup and set up markdown filter with it
        card_image_lookup = context.pop("_card_image_lookup", None)
        self.env.filters["markdown"] = lambda text, lookup=card_image_lookup: (
            Markup(simple_markdown_to_html(text, lookup)) if text else ""
        )

        return template.render(**context)

    def _get_archetype_cards(
        self,
        snapshot: MetaSnapshot,
        archetype: Archetype,
    ) -> list[Card]:
        """Get top performing cards for a specific archetype.

        Includes cards if:
        1. They have explicit win rate data for this archetype colors.
        2. Their color identity is a subset of the archetype colors (for 3-color archetypes).
        """
        matching_cards = []
        arch_colors_set = set(archetype.colors)
        
        for card in snapshot.all_cards:
            # Check 1: Explicit data match (preferred)
            if archetype.colors in card.stats.archetype_wrs:
                matching_cards.append(card)
                continue
                
            # Check 2: Subset logic (important for 3-color archetypes to show 2-color/mono cards)
            # Only include cards with some colors, and they must be a subset of the archetype
            if card.colors and set(card.colors).issubset(arch_colors_set):
                # We only add it if it's a reasonably good card (Grade C or better) 
                # to avoid cluttering 3-color lists with every single mono filler
                if card.composite_score >= 40:
                    matching_cards.append(card)

        # Sort by composite_score (descending)
        matching_cards.sort(key=lambda c: c.composite_score, reverse=True)

        return matching_cards

    def save_report(
        self,
        snapshot: MetaSnapshot,
        output_dir: str = "output",
        include_llm: bool = True,
        single_file: bool = False,
    ) -> str:
        """
        Generate and save HTML draft guide to file.

        Args:
            snapshot: MetaSnapshot to generate guide from
            output_dir: Output directory
            include_llm: Whether to include LLM analysis
            single_file: If True, generate legacy single-file HTML

        Returns:
            Path to saved HTML file or directory
        """
        if single_file:
            return self._save_single_file(snapshot, output_dir, include_llm)
        else:
            return self._save_multi_file(snapshot, output_dir, include_llm)

    def _save_single_file(
        self,
        snapshot: MetaSnapshot,
        output_dir: str,
        include_llm: bool,
    ) -> str:
        """Generate legacy single-file HTML output."""
        # Generate content using the original single-file template
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

    def _save_multi_file(
        self,
        snapshot: MetaSnapshot,
        output_dir: str,
        include_llm: bool,
    ) -> str:
        """Generate multi-file HTML output with shared CSS/JS."""
        # Create output directory structure
        timestamp = snapshot.timestamp.strftime("%Y-%m-%d")
        base_name = f"{snapshot.expansion}_{snapshot.format}_{timestamp}"
        report_dir = Path(output_dir) / base_name
        report_dir.mkdir(parents=True, exist_ok=True)

        # Create CSS/JS directories
        css_dir = report_dir / "css"
        js_dir = report_dir / "js"
        css_dir.mkdir(exist_ok=True)
        js_dir.mkdir(exist_ok=True)

        # Copy static assets
        static_dir = self.template_dir / "static"
        if (static_dir / "guide.css").exists():
            shutil.copy(static_dir / "guide.css", css_dir / "guide.css")
            logger.info(f"Copied guide.css to {css_dir}")
        if (static_dir / "guide.js").exists():
            shutil.copy(static_dir / "guide.js", js_dir / "guide.js")
            logger.info(f"Copied guide.js to {js_dir}")

        # Prepare common context
        context = self._prepare_context(snapshot, include_llm)

        # Extract card_image_lookup and set up markdown filter with it
        card_image_lookup = context.pop("_card_image_lookup", None)
        self.env.filters["markdown"] = lambda text, lookup=card_image_lookup: (
            Markup(simple_markdown_to_html(text, lookup)) if text else ""
        )

        # Generate each page
        for filename, template_name, active_page in self.PAGES:
            try:
                template = self.env.get_template(template_name)
                context["active_page"] = active_page
                context["page_title"] = active_page.title()
                content = template.render(**context)

                filepath = report_dir / filename
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info(f"Generated {filepath}")
            except Exception as e:
                logger.error(f"Failed to generate {filename}: {e}")
                raise

        logger.info(f"Multi-page HTML guide saved to {report_dir}")
        return str(report_dir)

    def _prepare_context(
        self,
        snapshot: MetaSnapshot,
        include_llm: bool,
    ) -> dict:
        """Prepare the template context dictionary."""
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

        # Build card name -> image URL lookup for AI analysis hover
        card_image_lookup = {
            card.name: card.image_uri
            for card in snapshot.all_cards
            if card.image_uri
        }

        return {
            # Meta info
            "expansion": snapshot.expansion,
            "format": snapshot.format,
            "timestamp": snapshot.timestamp.strftime("%Y-%m-%d %H:%M"),
            "total_cards": snapshot.total_cards,
            "total_games": snapshot.total_games_analyzed,

            # Format characteristics
            "format_speed": snapshot.format_speed,
            "splash_indicator": snapshot.splash_indicator,

            # Trophy deck statistics (optional)
            "trophy_stats": snapshot.trophy_stats,

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

            # Grade display (17lands-style 13 grades)
            "grade_order": ["A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "D-", "F"],

            # LLM analysis (optional)
            "llm_color_strategy": snapshot.llm_color_strategy if include_llm else None,
            "llm_strategy": snapshot.llm_strategy_tips if include_llm else None,
            "llm_format_overview": snapshot.llm_format_overview if include_llm else None,
            "llm_format_characteristics": snapshot.llm_format_characteristics if include_llm else None,
            "llm_archetype_deep_dive": snapshot.llm_archetype_deep_dive if include_llm else None,

            # Card image lookup for AI analysis hover
            "_card_image_lookup": card_image_lookup,
        }
