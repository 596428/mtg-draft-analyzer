"""Prompt building for LLM analysis."""

from typing import Optional

from src.models.card import Card
from src.models.meta import MetaSnapshot


META_ANALYSIS_PROMPT = '''You are an expert MTG draft analyst. Analyze the following draft meta data for {expansion} {format} and provide strategic insights.

## Current Meta Overview

**Total Cards Analyzed**: {total_cards}
**Total Games**: {total_games:,}

### Color Rankings (by strength)
{color_rankings}

### Top Archetypes (by win rate)
{archetype_rankings}

### Top Performing Cards
{top_cards}

### Sleeper Cards (Undervalued)
{sleeper_cards}

### Trap Cards (Overvalued)
{trap_cards}

---

Please provide analysis on:

1. **Meta Summary**: What defines this draft format? Is it fast/slow? Synergy-driven or value-driven?

2. **Color Assessment**: Which colors are strongest and why? Are there any colors to avoid?

3. **Top Archetypes**: What makes the best archetypes successful? Key strategies for each.

4. **Draft Strategy**:
   - What should I prioritize in pack 1?
   - How should I read signals?
   - When should I pivot?

5. **Sleeper Insights**: Why might these sleeper cards be undervalued? In what situations do they shine?

6. **Trap Analysis**: Why are these trap cards underperforming? What makes them look better than they are?

Please be specific and actionable. Reference actual card names and win rates where helpful.

**중요**: 모든 분석 결과를 한글로 작성해주세요. 단, 카드 이름, 색깔 약어(W, U, B, R, G), 아키타입 이름(Selesnya, Golgari 등)은 영어 원문을 유지합니다.
'''


CARD_ANALYSIS_PROMPT = '''Analyze this MTG card's draft performance:

**Card**: {name}
**Colors**: {colors}
**Mana Cost**: {mana_cost}
**Type**: {type_line}
**Card Text**: {oracle_text}

## Performance Data

- **Composite Score**: {score:.1f} (Grade: {grade})
- **GIH Win Rate**: {gih_wr:.2%} (Bayesian adjusted: {adj_wr:.2%})
- **Games Analyzed**: {games:,}
- **Average Last Seen At**: {alsa:.1f} (pick {pick_position})
- **Improvement When Drawn**: {iwd:.2%}

## Archetype Performance
{archetype_breakdown}

## Classification
- **Irregularity**: {irregularity_type} (Z-score: {z_score:.2f})
- **Stability**: {stability:.1f}% ({stability_class})

---

Please analyze:

1. Why is this card performing at this level?
2. What situations make this card good/bad?
3. In which archetypes should I prioritize this card?
4. Are there common mistakes players make with this card?
5. Draft pick priority guidance (when to take it, when to pass).

**중요**: 분석 결과를 한글로 작성해주세요. 카드 이름은 영어 원문을 유지합니다.
'''


STRATEGY_TIPS_PROMPT = '''Based on this meta data for {expansion} {format}, provide 5-7 concise, actionable draft tips:

**Top Colors**: {top_colors}
**Top Archetypes**: {top_archetypes}
**Key Sleepers**: {key_sleepers}
**Key Traps**: {key_traps}

Format your response as a numbered list of strategic tips. Each tip should be:
- Specific to this format
- Actionable during a draft
- Backed by the data provided

**중요**: 팁을 한글로 작성해주세요. 카드 이름과 아키타입 이름은 영어로 유지합니다.
'''


class PromptBuilder:
    """Builds prompts for LLM analysis."""

    def __init__(
        self,
        meta_template: Optional[str] = None,
        card_template: Optional[str] = None,
        strategy_template: Optional[str] = None,
    ):
        """
        Initialize prompt builder.

        Args:
            meta_template: Custom meta analysis template
            card_template: Custom card analysis template
            strategy_template: Custom strategy tips template
        """
        self.meta_template = meta_template or META_ANALYSIS_PROMPT
        self.card_template = card_template or CARD_ANALYSIS_PROMPT
        self.strategy_template = strategy_template or STRATEGY_TIPS_PROMPT

    def build_meta_prompt(self, snapshot: MetaSnapshot) -> str:
        """Build meta analysis prompt from snapshot."""
        # Format color rankings
        color_rankings = "\n".join(
            f"{i+1}. **{c.color}** - Score: {c.strength_score:.1f}, "
            f"Playables: {c.playable_count}"
            for i, c in enumerate(snapshot.top_colors)
        )

        # Format archetype rankings
        archetype_rankings = "\n".join(
            f"{i+1}. **{a.guild_name}** ({a.colors}) - "
            f"WR: {a.win_rate:.2%}, Score: {a.strength_score:.1f}"
            for i, a in enumerate(snapshot.top_archetypes[:10])
        )

        # Format top cards
        top_cards = "\n".join(
            f"- **{c.name}** ({c.colors}, {c.rarity.value}) - "
            f"Grade: {c.grade}, GIH WR: {c.stats.gih_wr:.2%}"
            for c in snapshot.top_cards[:15]
        )

        # Format sleepers
        sleeper_cards = "\n".join(
            f"- **{c.name}** ({c.colors}) - "
            f"Grade: {c.grade}, GIH WR: {c.stats.gih_wr:.2%}, "
            f"Z: +{c.irregularity_z:.2f}"
            for c in snapshot.sleeper_cards[:7]
        ) or "No significant sleepers detected."

        # Format traps
        trap_cards = "\n".join(
            f"- **{c.name}** ({c.colors}) - "
            f"Grade: {c.grade}, GIH WR: {c.stats.gih_wr:.2%}, "
            f"Z: {c.irregularity_z:.2f}"
            for c in snapshot.trap_cards[:7]
        ) or "No significant traps detected."

        return self.meta_template.format(
            expansion=snapshot.expansion,
            format=snapshot.format,
            total_cards=snapshot.total_cards,
            total_games=snapshot.total_games_analyzed,
            color_rankings=color_rankings,
            archetype_rankings=archetype_rankings,
            top_cards=top_cards,
            sleeper_cards=sleeper_cards,
            trap_cards=trap_cards,
        )

    def build_card_prompt(self, card: Card) -> str:
        """Build card analysis prompt."""
        # Format archetype breakdown
        archetype_breakdown = ""
        if card.stats.archetype_wrs:
            lines = []
            for colors, wr in sorted(
                card.stats.archetype_wrs.items(),
                key=lambda x: x[1],
                reverse=True
            ):
                games = card.stats.archetype_games.get(colors, 0)
                lines.append(f"- {colors}: {wr:.2%} ({games:,} games)")
            archetype_breakdown = "\n".join(lines)
        else:
            archetype_breakdown = "No archetype-specific data available."

        # Determine stability class
        if card.stability_score >= 80:
            stability_class = "Very Stable"
        elif card.stability_score >= 60:
            stability_class = "Stable"
        elif card.stability_score >= 40:
            stability_class = "Moderate"
        else:
            stability_class = "Synergy-Dependent"

        # Calculate pick position from ALSA
        pick_position = int(card.stats.alsa + 0.5)

        return self.card_template.format(
            name=card.name,
            colors=card.colors,
            mana_cost=card.mana_cost or "N/A",
            type_line=card.type_line or "N/A",
            oracle_text=card.oracle_text or "N/A",
            score=card.composite_score,
            grade=card.grade,
            gih_wr=card.stats.gih_wr,
            adj_wr=card.adjusted_gih_wr,
            games=card.stats.gih_games,
            alsa=card.stats.alsa,
            pick_position=pick_position,
            iwd=card.stats.iwd,
            archetype_breakdown=archetype_breakdown,
            irregularity_type=card.irregularity_type.title(),
            z_score=card.irregularity_z,
            stability=card.stability_score,
            stability_class=stability_class,
        )

    def build_strategy_prompt(self, snapshot: MetaSnapshot) -> str:
        """Build strategy tips prompt."""
        top_colors = ", ".join(c.color for c in snapshot.top_colors[:3])
        top_archetypes = ", ".join(
            f"{a.guild_name}" for a in snapshot.top_archetypes[:5]
        )
        key_sleepers = ", ".join(
            c.name for c in snapshot.sleeper_cards[:5]
        ) or "None"
        key_traps = ", ".join(
            c.name for c in snapshot.trap_cards[:5]
        ) or "None"

        return self.strategy_template.format(
            expansion=snapshot.expansion,
            format=snapshot.format,
            top_colors=top_colors,
            top_archetypes=top_archetypes,
            key_sleepers=key_sleepers,
            key_traps=key_traps,
        )


def build_meta_prompt(snapshot: MetaSnapshot) -> str:
    """Convenience function to build meta prompt."""
    builder = PromptBuilder()
    return builder.build_meta_prompt(snapshot)


def build_card_prompt(card: Card) -> str:
    """Convenience function to build card prompt."""
    builder = PromptBuilder()
    return builder.build_card_prompt(card)
