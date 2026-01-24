"""Markdown report generation."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.models.archetype import Archetype, ColorStrength
from src.models.card import Card, Rarity
from src.models.meta import MetaSnapshot

logger = logging.getLogger(__name__)

# Default template if file not found
DEFAULT_TEMPLATE = '''# {{ expansion }} {{ format }} Meta Analysis

**Generated**: {{ timestamp }}
**Total Cards**: {{ total_cards }}
**Total Games Analyzed**: {{ total_games | format_number }}

---

## 🎨 Color Rankings

| Rank | Color | Strength | Top Common | Top Uncommon | Playables |
|------|-------|----------|------------|--------------|-----------|
{% for c in color_strengths %}
| {{ c.rank }} | {{ c.color }} | {{ c.strength_score | round(1) }} | {{ c.top_commons[0] if c.top_commons else '-' }} | {{ c.top_uncommons[0] if c.top_uncommons else '-' }} | {{ c.playable_count }} |
{% endfor %}

---

## 🏛️ Archetype Rankings (Two-Color)

| Rank | Archetype | Win Rate | Strength | Synergy Lift | Key Common | Signpost |
|------|-----------|----------|----------|--------------|------------|----------|
{% for a in archetypes[:10] %}
| {{ a.rank }} | {{ a.guild_name }} ({{ a.colors }}) | {{ (a.win_rate * 100) | round(2) }}% | {{ a.strength_score | round(1) }} | {{ (a.synergy_lift * 100) | round(2) }}%p | {{ a.key_commons[0] if a.key_commons else '-' }} | {{ a.signpost_uncommon or '-' }} |
{% endfor %}

---

{% if format_speed %}
## 📈 포맷 특성

### 속도
- **속도 등급**: {{ format_speed.speed_label }}
- **Tempo Ratio (OH/GD)**: {{ format_speed.tempo_ratio | round(4) }}
- **저마나 우위**: {{ (format_speed.aggro_advantage * 100) | round(2) }}%p
- **추천 전략**: {{ format_speed.recommendation }}

| 지표 | 값 |
|------|-----|
| 평균 OH WR | {{ (format_speed.avg_oh_wr * 100) | round(2) }}% |
| 평균 GD WR | {{ (format_speed.avg_gd_wr * 100) | round(2) }}% |
| 저마나(CMC≤2) WR | {{ (format_speed.low_cmc_wr * 100) | round(2) }}% |
| 고마나(CMC≥5) WR | {{ (format_speed.high_cmc_wr * 100) | round(2) }}% |

{% if format_speed.conflicts %}
**⚠️ 지표 충돌**:
{% for conflict in format_speed.conflicts %}
- {{ conflict }}
{% endfor %}
{% endif %}
{% endif %}

{% if splash_indicator %}
### 스플래시 분석
- **스플래시 선호도**: {{ splash_indicator.splash_label }}
- **듀얼 랜드 ALSA**: {{ splash_indicator.dual_land_alsa | round(2) }}
- **듀얼 랜드 픽률**: {{ (splash_indicator.dual_land_pick_rate * 100) | round(1) }}%
- **마나 픽서 WR 프리미엄**: {{ (splash_indicator.fixer_wr_premium * 100) | round(2) }}%p
- **추천**: {{ splash_indicator.recommendation }}

| 카드 유형 | 수량 |
|----------|------|
| 듀얼 랜드 | {{ splash_indicator.dual_land_count }} |
| 마나 픽서 | {{ splash_indicator.mana_fixer_count }} |
{% endif %}

---

## ⭐ Top 20 Cards by Composite Score

| Rank | Card | Colors | Rarity | Grade | Score | GIH WR |
|------|------|--------|--------|-------|-------|--------|
{% for c in top_cards[:20] %}
| {{ loop.index }} | {% if c.scryfall_uri %}[{{ c.name }}]({{ c.scryfall_uri }}){% else %}{{ c.name }}{% endif %} | {{ c.colors }} | {{ c.rarity.value | title }} | {{ c.grade }} | {{ c.composite_score | round(1) }} | {{ (c.stats.gih_wr * 100) | round(2) }}% |
{% endfor %}

---

## 💎 Sleeper Cards (Undervalued)

Cards performing better than their pick rate suggests:

| Card | Colors | Grade | Score | GIH WR | Deviation Z |
|------|--------|-------|-------|--------|-------------|
{% for c in sleepers[:10] %}
| {% if c.scryfall_uri %}[{{ c.name }}]({{ c.scryfall_uri }}){% else %}{{ c.name }}{% endif %} | {{ c.colors }} | {{ c.grade }} | {{ c.composite_score | round(1) }} | {{ (c.stats.gih_wr * 100) | round(2) }}% | +{{ c.irregularity_z | round(2) }} |
{% endfor %}

{% if not sleepers %}
*No significant sleepers detected.*
{% endif %}

---

## ⚠️ Trap Cards (Overvalued)

Cards performing worse than their pick rate suggests:

| Card | Colors | Grade | Score | GIH WR | Deviation Z |
|------|--------|-------|-------|--------|-------------|
{% for c in traps[:10] %}
| {% if c.scryfall_uri %}[{{ c.name }}]({{ c.scryfall_uri }}){% else %}{{ c.name }}{% endif %} | {{ c.colors }} | {{ c.grade }} | {{ c.composite_score | round(1) }} | {{ (c.stats.gih_wr * 100) | round(2) }}% | {{ c.irregularity_z | round(2) }} |
{% endfor %}

{% if not traps %}
*No significant traps detected.*
{% endif %}

---

## 📊 Color Breakdown

{% for color in color_strengths %}
### {{ color.color }} - Rank {{ color.rank }} (Score: {{ color.strength_score | round(1) }})

**Top Commons**: {{ color.top_commons[:5] | join(', ') or 'N/A' }}

**Top Uncommons**: {{ color.top_uncommons[:3] | join(', ') or 'N/A' }}

**Top Rares**: {{ color.top_rares[:3] | join(', ') or 'N/A' }}

{% endfor %}

---

{% if llm_analysis %}
## 🤖 AI Strategic Analysis

{{ llm_analysis }}
{% endif %}

{% if llm_strategy %}
## 📝 Strategy Tips

{{ llm_strategy }}
{% endif %}

---

## 🖼️ Top Card Images

{% set cards_with_images = top_cards[:20] | selectattr('image_uri') | list %}
{% if cards_with_images %}
<div style="display: flex; flex-wrap: wrap; gap: 10px; justify-content: center;">
{% for c in cards_with_images[:12] %}
<div style="text-align: center; width: 200px;">
{% if c.scryfall_uri %}<a href="{{ c.scryfall_uri }}">{% endif %}
<img src="{{ c.image_uri }}" alt="{{ c.name }}" style="width: 200px;">
{% if c.scryfall_uri %}</a>{% endif %}
<br><small>{{ c.name }}</small>
</div>
{% endfor %}
</div>
{% else %}
*Card images not available.*
{% endif %}

---

*Report generated by MTG Draft Analyzer*
'''


class MarkdownReportGenerator:
    """Generates Markdown reports from MetaSnapshot."""

    def __init__(
        self,
        template_dir: str = "templates",
        template_name: str = "meta_report.md.j2",
    ):
        """
        Initialize report generator.

        Args:
            template_dir: Directory containing Jinja2 templates
            template_name: Name of template file
        """
        self.template_dir = Path(template_dir)
        self.template_name = template_name

        # Set up Jinja2 environment (no autoescape for Markdown)
        if self.template_dir.exists():
            self.env = Environment(
                loader=FileSystemLoader(str(self.template_dir)),
                autoescape=False,  # Markdown doesn't need HTML escaping
            )
        else:
            self.env = Environment(autoescape=False)

        # Add custom filters
        self.env.filters["format_number"] = lambda n: f"{n:,}"

    def _get_template(self) -> str:
        """Get template content."""
        template_path = self.template_dir / self.template_name

        if template_path.exists():
            return template_path.read_text(encoding="utf-8")
        else:
            logger.warning(
                f"Template not found at {template_path}, using default"
            )
            return DEFAULT_TEMPLATE

    def generate_markdown(
        self,
        snapshot: MetaSnapshot,
        include_llm: bool = True,
    ) -> str:
        """
        Generate Markdown report from meta snapshot.

        Args:
            snapshot: MetaSnapshot to report on
            include_llm: Whether to include LLM analysis

        Returns:
            Markdown string
        """
        template = self.env.from_string(self._get_template())

        context = {
            "expansion": snapshot.expansion,
            "format": snapshot.format,
            "timestamp": snapshot.timestamp.strftime("%Y-%m-%d %H:%M"),
            "total_cards": snapshot.total_cards,
            "total_games": snapshot.total_games_analyzed,
            "color_strengths": snapshot.top_colors,
            "archetypes": snapshot.top_archetypes,
            "top_cards": snapshot.top_cards[:20],
            "sleepers": snapshot.sleeper_cards[:10],
            "traps": snapshot.trap_cards[:10],
            "format_speed": snapshot.format_speed,
            "splash_indicator": snapshot.splash_indicator,
            "llm_analysis": snapshot.llm_meta_analysis if include_llm else None,
            "llm_strategy": snapshot.llm_strategy_tips if include_llm else None,
        }

        return template.render(**context)

    def generate_color_report(
        self,
        snapshot: MetaSnapshot,
        color: str,
    ) -> str:
        """
        Generate detailed report for a single color.

        Args:
            snapshot: MetaSnapshot
            color: Color to report on (W, U, B, R, G)

        Returns:
            Markdown string
        """
        color_strength = next(
            (c for c in snapshot.color_strengths if c.color == color),
            None
        )

        if not color_strength:
            return f"# {color} - No data available"

        color_cards = snapshot.get_cards_by_color(color)
        color_cards.sort(key=lambda c: c.composite_score, reverse=True)

        lines = [
            f"# {color} Color Analysis",
            "",
            f"**Rank**: {color_strength.rank} / 5",
            f"**Strength Score**: {color_strength.strength_score:.1f}",
            f"**Playable Cards**: {color_strength.playable_count}",
            "",
            "## Top Cards by Rarity",
            "",
            "### Commons",
            "",
        ]

        # Add commons
        commons = [c for c in color_cards if c.rarity == Rarity.COMMON][:10]
        for i, card in enumerate(commons, 1):
            lines.append(
                f"{i}. **{card.name}** ({card.grade}) - "
                f"Score: {card.composite_score:.1f}, "
                f"GIH WR: {card.stats.gih_wr*100:.1f}%"
            )

        lines.extend(["", "### Uncommons", ""])

        # Add uncommons
        uncommons = [c for c in color_cards if c.rarity == Rarity.UNCOMMON][:5]
        for i, card in enumerate(uncommons, 1):
            lines.append(
                f"{i}. **{card.name}** ({card.grade}) - "
                f"Score: {card.composite_score:.1f}, "
                f"GIH WR: {card.stats.gih_wr*100:.1f}%"
            )

        lines.extend(["", "### Rares/Mythics", ""])

        # Add rares
        rares = [
            c for c in color_cards
            if c.rarity in (Rarity.RARE, Rarity.MYTHIC)
        ][:5]
        for i, card in enumerate(rares, 1):
            lines.append(
                f"{i}. **{card.name}** ({card.grade}) - "
                f"Score: {card.composite_score:.1f}, "
                f"GIH WR: {card.stats.gih_wr*100:.1f}%"
            )

        return "\n".join(lines)

    def save_report(
        self,
        snapshot: MetaSnapshot,
        output_dir: str = "output",
        include_llm: bool = True,
    ) -> str:
        """
        Generate and save Markdown report to file.

        Args:
            snapshot: MetaSnapshot to report on
            output_dir: Output directory
            include_llm: Whether to include LLM analysis

        Returns:
            Path to saved file
        """
        # Generate content
        content = self.generate_markdown(snapshot, include_llm)

        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        # Generate filename
        timestamp = snapshot.timestamp.strftime("%Y-%m-%d")
        filename = f"{snapshot.expansion}_{snapshot.format}_{timestamp}_meta_report.md"
        filepath = output_path / filename

        # Write file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        logger.info(f"Report saved to {filepath}")

        return str(filepath)
