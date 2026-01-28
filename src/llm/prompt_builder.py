"""Prompt building for LLM analysis."""

from typing import Optional

from src.data.set_metadata import get_mechanic_names, get_set_mechanics
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

---

Please provide analysis on:

1. **Meta Summary**: What defines this draft format? Is it fast/slow? Synergy-driven or value-driven?

2. **🎨 Color Strategy (색상 전략)**:
   - **모든 5개 색상** (W, U, B, R, G) 각각에 대해 분석
   - 각 색상별: 강점, 약점, 상위 커먼 3장
   - **P1P1 색상 우선순위** (Pack 1 Pick 1에서 어떤 색상 카드를 우선해야 하는가와 그 이유)

Please be specific and actionable. Reference actual card names and win rates where helpful.

**중요**: 모든 분석 결과를 한글로 작성해주세요. 단, 카드 이름, 색깔 약어(W, U, B, R, G), 아키타입 이름(Selesnya, Golgari 등)은 영어 원문을 유지합니다.

⚠️ **출력 형식 주의**:
- 서론/인사말 없이 바로 분석 내용으로 시작
- "분석해 드리겠습니다", "살펴보겠습니다", "제시된 데이터를 바탕으로" 등 문구 금지
- 마무리 문구 없이 분석 완료 후 바로 종료
- "도움이 되셨으면", "추가 질문이 있으시면" 등 마무리 문구 금지
'''


COLOR_STRATEGY_PROMPT = '''You are an expert MTG draft analyst. Analyze the following color data for {expansion} {format}.

## Color Rankings (by strength)
{color_rankings}

## Top Archetypes (by win rate)
{archetype_rankings}

## Top Performing Cards
{top_cards}

## Color Details
{color_details}

---

Please provide analysis on:

**🎨 Color Strategy (색상 전략)**:
- **모든 5개 색상** (W, U, B, R, G) 각각에 대해 분석
- 각 색상별: 강점, 약점, 상위 커먼 3장
- **P1P1 색상 우선순위** (Pack 1 Pick 1에서 어떤 색상 카드를 우선해야 하는가와 그 이유)

Please be specific and actionable. Reference actual card names and win rates where helpful.

**중요**: 모든 분석 결과를 한글로 작성해주세요. 단, 카드 이름, 색깔 약어(W, U, B, R, G), 아키타입 이름(Selesnya, Golgari 등)은 영어 원문을 유지합니다.

⚠️ **출력 형식 주의**:
- 서론/인사말 없이 바로 분석 내용으로 시작
- "분석해 드리겠습니다", "살펴보겠습니다" 등 문구 금지
- 마무리 문구 없이 분석 완료 후 바로 종료
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
- **Viability**: {viable_archetypes} archetypes ({viability_class})

---

Please analyze:

1. Why is this card performing at this level?
2. What situations make this card good/bad?
3. In which archetypes should I prioritize this card?
4. Are there common mistakes players make with this card?
5. Draft pick priority guidance (when to take it, when to pass).

**중요**: 분석 결과를 한글로 작성해주세요. 카드 이름은 영어 원문을 유지합니다.
'''


FORMAT_OVERVIEW_PROMPT = '''당신은 MTG 드래프트 전문가입니다.
다음 데이터를 분석하여 **데이터 너머의 인사이트**를 제공해주세요.

## 핵심 질문 (반드시 답변)
1. **왜** 상위 아키타입이 강한가? (단순히 "강하다"가 아니라 메커니즘 설명)
2. 각 아키타입은 **서로 다른 전략**을 사용하는가? (공통점과 차이점)
3. Pack 1 Pick 1에서 **구체적인** 우선순위는?

⚠️ **중요**: 1위 아키타입의 메커니즘이 포맷 전체를 대표하지 않습니다.
각 아키타입은 **독립적인 전략**을 가집니다. 분석 시 반드시 구분하세요.

{set_mechanics}

## 포맷 데이터
- 세트: {expansion} ({format})
- 게임 수: {total_games:,}판

## 포맷 속도
- Tempo Ratio: {tempo_ratio:.3f} (OH WR / GD WR)
- Speed: {speed_label}
- Aggro Advantage: {aggro_advantage:.3f}
- Low CMC WR (≤2): {low_cmc_wr:.2%} vs High CMC WR (≥5): {high_cmc_wr:.2%}
- 갈등 감지: {conflicts}

## 스플래시 분석
- Splash Viability: {splash_label}
- Dual Land Count: {dual_land_count}장
- Dual Land ALSA: {dual_land_alsa:.1f}
- Fixer WR Premium: {fixer_wr_premium:.2%}

## 색상 분석 (상세)
{color_details}

## 아키타입 분석 (상세)
{archetype_details}

{trophy_stats_section}

---

## 출력 형식 (2개 섹션)

### 1. 📋 포맷 특성 (왜 이런 메타인가)
- 이 포맷에서 **공존하는** 주요 전략들은? (예: 어그로, 미드레인지, 컨트롤)
- **주의**: 1위 아키타입의 전략이 포맷 전체를 정의하지 않습니다
- 각 색상 조합별로 **서로 다른** 메커니즘이 존재합니다
- 다른 세트와 차별화되는 특징은?
- 속도 갈등이 있다면 실전적 해석

### 2. 🏆 상위 아키타입 심층 분석
⚠️ 각 아키타입은 **독립적인 전략**을 가집니다. 1위의 전략 ≠ 포맷 전체 전략

각 아키타입(상위 4개)마다:
- 이 아키타입**만의** 고유 메커니즘 (다른 아키타입과 구별되는 점)
- 핵심 시너지 카드 3장과 **왜 이 아키타입에서만 작동하는지**
- 이 아키타입에서 피해야 할 카드 (다른 아키타입에서는 좋을 수 있음)

---

한글로 작성하세요 (카드명/색상 약어/아키타입명은 영문 유지).
'''


FORMAT_CHARACTERISTICS_PROMPT = '''당신은 MTG 드래프트 전문가입니다.
다음 데이터를 분석하여 **포맷 특성**에 대한 인사이트를 제공해주세요.

## 핵심 질문 (반드시 답변)
1. 이 포맷을 정의하는 핵심 특징은?
2. 이 포맷의 **속도**는? (데이터 기반 근거 제시)
3. 스플래시가 **언제 적합한가**?

{set_mechanics}

## 포맷 데이터
- 세트: {expansion} ({format})
- 게임 수: {total_games:,}판

### 아키타입 순위
{archetype_rankings}

### 포맷 속도
- Tempo Ratio: {tempo_ratio:.3f} (OH WR / GD WR)
- Speed: {speed_label}
- Aggro Advantage: {aggro_advantage:.3f}
- Low CMC WR (≤2): {low_cmc_wr:.2%} vs High CMC WR (≥5): {high_cmc_wr:.2%}
- 갈등 감지: {conflicts}

### 스플래시 분석
- Splash Viability: {splash_label}
- Dual Land Count: {dual_land_count}장
- Dual Land ALSA: {dual_land_alsa:.1f}
- Fixer WR Premium: {fixer_wr_premium:.2%}

### 키워드/메커니즘 색상별 분포
{keyword_distribution}

---

## 출력 형식

### 1. 📊 메타 요약
- 이 포맷을 정의하는 핵심 특징 (2-3문장)
- 시너지 중심 vs 밸류 중심
- 가장 강력한 아키타입 조합

### 2. ⏱️ 포맷 속도 분석
- 데이터 기반 속도 해석 (aggro vs control)
- tempo_ratio, CMC별 승률의 실전적 의미
- 속도 갈등이 있다면 그 해석

### 3. 💧 스플래시 가이드
- 스플래시가 적합한 상황
- 듀얼 랜드/픽서 우선순위
- 스플래시 리스크

### 4. ⭐ 세트 특징
- 이 세트만의 독특한 특징
- 드래프트 시 유의사항

---

**중요**: 한글로 작성 (카드명/색상 약어/아키타입명은 영문 유지).

⚠️ **출력 형식 주의**:
- 서론 없이 "### 1. 📊 메타 요약"으로 바로 시작
- 마무리 문구 없이 분석 완료 후 바로 종료
'''


ARCHETYPE_DEEP_DIVE_PROMPT = '''당신은 MTG 드래프트 전문가입니다.
다음 데이터를 분석하여 **상위 아키타입**에 대한 심층 분석을 제공해주세요.

## 핵심 질문 (반드시 답변)
1. **왜** 이 아키타입이 강한가? (단순히 "강하다"가 아니라 메커니즘 설명)
2. 각 아키타입은 **서로 다른 전략**을 사용하는가?
3. 각 아키타입의 **핵심 시너지**는?

⚠️ **중요**: 각 아키타입은 **독립적인 전략**을 가집니다.
1위 아키타입의 전략이 포맷 전체를 대표하지 않습니다.

{set_mechanics}

## 포맷 데이터
- 세트: {expansion} ({format})
- 게임 수: {total_games:,}판

## 아키타입 분석 (상세)
{archetype_details}

{trophy_stats_section}

---

## 출력 형식: 🏆 상위 아키타입 심층 분석

⚠️ 각 아키타입은 **독립적인 전략**을 가집니다. 1위의 전략 ≠ 포맷 전체 전략

각 아키타입(상위 4개)마다 다음을 작성해주세요:

### [아키타입명] (색상) - Rank #N

#### 1. 아키타입 정체성
- 이 아키타입**만의** 고유 메커니즘 (다른 아키타입과 구별되는 점)
- 승리 조건 (어떻게 게임을 이기는가)
- 속도 프로필 (aggro/midrange/control)

#### 2. 핵심 시너지 카드 3장
- 각 카드가 **왜 이 아키타입에서만 작동하는지** 설명
- 다른 아키타입에서의 성능과 비교

#### 3. 드래프트 우선순위
- 초기 픽에서 노려야 할 카드
- 후반 픽에서 줍기 좋은 카드
- 이 아키타입에서 피해야 할 카드 (다른 아키타입에서는 좋을 수 있음)

#### 4. 플레이 패턴
- 마나 커브 구성
- 멀리건 기준
- 사이드보딩 고려사항

---

한글로 작성하세요 (카드명/색상 약어/아키타입명은 영문 유지).

⚠️ **출력 형식 주의**:
- 서론/인사말 없이 첫 아키타입 분석으로 바로 시작
- "분석해 드리겠습니다", "살펴보겠습니다", "제시된 데이터를 바탕으로" 등 문구 금지
- 마무리 문구 없이 분석 완료 후 바로 종료
- "도움이 되셨으면", "추가 질문이 있으시면" 등 마무리 문구 금지
'''


STRATEGY_TIPS_PROMPT = '''Based on this meta data for {expansion} {format}, provide 5-7 concise, actionable draft tips:

**Top Colors**: {top_colors}
**Top Archetypes**: {top_archetypes}

Format your response as a numbered list of strategic tips. Each tip should be:
- Specific to this format
- Actionable during a draft
- Backed by the data provided

**중요**: 팁을 한글로 작성해주세요. 카드 이름과 아키타입 이름은 영어로 유지합니다.

⚠️ **출력 형식 주의**:
- 서론/인사말 없이 바로 1번 팁부터 시작
- "제공해주신 데이터를 바탕으로", "정리해 드립니다" 등 문구 금지
- 마무리 문구 없이 마지막 팁 작성 후 바로 종료
'''


class PromptBuilder:
    """Builds prompts for LLM analysis."""

    def __init__(
        self,
        meta_template: Optional[str] = None,
        card_template: Optional[str] = None,
        strategy_template: Optional[str] = None,
        format_overview_template: Optional[str] = None,
        format_characteristics_template: Optional[str] = None,
        archetype_deep_dive_template: Optional[str] = None,
        color_strategy_template: Optional[str] = None,
    ):
        """
        Initialize prompt builder.

        Args:
            meta_template: Custom meta analysis template
            card_template: Custom card analysis template
            strategy_template: Custom strategy tips template
            format_overview_template: Custom format overview template
            format_characteristics_template: Custom format characteristics template
            archetype_deep_dive_template: Custom archetype deep dive template
            color_strategy_template: Custom color strategy template
        """
        self.meta_template = meta_template or META_ANALYSIS_PROMPT
        self.card_template = card_template or CARD_ANALYSIS_PROMPT
        self.strategy_template = strategy_template or STRATEGY_TIPS_PROMPT
        self.format_overview_template = format_overview_template or FORMAT_OVERVIEW_PROMPT
        self.format_characteristics_template = format_characteristics_template or FORMAT_CHARACTERISTICS_PROMPT
        self.archetype_deep_dive_template = archetype_deep_dive_template or ARCHETYPE_DEEP_DIVE_PROMPT
        self.color_strategy_template = color_strategy_template or COLOR_STRATEGY_PROMPT

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

        return self.meta_template.format(
            expansion=snapshot.expansion,
            format=snapshot.format,
            total_cards=snapshot.total_cards,
            total_games=snapshot.total_games_analyzed,
            color_rankings=color_rankings,
            archetype_rankings=archetype_rankings,
            top_cards=top_cards,
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

        # Determine viability class
        if card.viable_archetypes == 0:
            viability_class = "No data"
        elif card.viable_archetypes >= 5:
            viability_class = "Very Flexible"
        elif card.viable_archetypes >= 3:
            viability_class = "Flexible"
        elif card.viable_archetypes >= 2:
            viability_class = "Moderate"
        else:
            viability_class = "Archetype-Specific"

        # Calculate pick position from ALSA
        pick_position = int(card.stats.alsa + 0.5)

        # Handle None values for win rates
        gih_wr = card.stats.gih_wr if card.stats.gih_wr is not None else 0.0
        iwd = card.stats.iwd if card.stats.iwd is not None else 0.0

        return self.card_template.format(
            name=card.name,
            colors=card.colors,
            mana_cost=card.mana_cost or "N/A",
            type_line=card.type_line or "N/A",
            oracle_text=card.oracle_text or "N/A",
            score=card.composite_score,
            grade=card.grade,
            gih_wr=gih_wr,
            adj_wr=card.adjusted_gih_wr,
            games=card.stats.gih_games,
            alsa=card.stats.alsa,
            pick_position=pick_position,
            iwd=iwd,
            archetype_breakdown=archetype_breakdown,
            irregularity_type=card.irregularity_type.title(),
            z_score=card.irregularity_z,
            viable_archetypes=card.viable_archetypes,
            viability_class=viability_class,
        )

    def build_strategy_prompt(self, snapshot: MetaSnapshot) -> str:
        """Build strategy tips prompt."""
        top_colors = ", ".join(c.color for c in snapshot.top_colors[:3])
        top_archetypes = ", ".join(
            f"{a.guild_name}" for a in snapshot.top_archetypes[:5]
        )

        return self.strategy_template.format(
            expansion=snapshot.expansion,
            format=snapshot.format,
            top_colors=top_colors,
            top_archetypes=top_archetypes,
        )

    def build_color_strategy_prompt(self, snapshot: MetaSnapshot) -> str:
        """Build color strategy prompt (META_ANALYSIS style).

        This generates detailed analysis for all 5 colors with:
        - Strengths and weaknesses
        - Top 3 commons per color
        - P1P1 color priority
        """
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

        # Format detailed color data (with top commons/uncommons)
        color_details = self._format_color_details(snapshot.top_colors)

        return self.color_strategy_template.format(
            expansion=snapshot.expansion,
            format=snapshot.format,
            color_rankings=color_rankings,
            archetype_rankings=archetype_rankings,
            top_cards=top_cards,
            color_details=color_details,
        )

    def build_format_overview_prompt(self, snapshot: MetaSnapshot) -> str:
        """Build comprehensive format overview prompt with detailed insight data."""
        # Format speed data (with defaults for missing data)
        fs = snapshot.format_speed
        tempo_ratio = fs.tempo_ratio if fs else 1.0
        speed_label = fs.speed_label if fs else "보통"
        aggro_advantage = fs.aggro_advantage if fs else 0.0
        low_cmc_wr = fs.low_cmc_wr if fs else 0.5
        high_cmc_wr = fs.high_cmc_wr if fs else 0.5
        conflicts = ", ".join(fs.conflicts) if fs and fs.conflicts else "없음"

        # Splash indicator data (with defaults)
        si = snapshot.splash_indicator
        splash_label = si.splash_label if si else "보통"
        dual_land_count = si.dual_land_count if si else 0
        dual_land_alsa = si.dual_land_alsa if si else 7.0
        fixer_wr_premium = si.fixer_wr_premium if si else 0.0

        # Format detailed color data
        color_details = self._format_color_details(snapshot.top_colors)

        # Format detailed archetype data
        archetype_details = self._format_archetype_details(snapshot.top_archetypes[:5])

        # Get set mechanics if available
        set_mechanics = get_set_mechanics(snapshot.expansion)

        # Format trophy stats section if available
        trophy_stats_section = self._format_trophy_stats(snapshot.trophy_stats)

        return self.format_overview_template.format(
            expansion=snapshot.expansion,
            format=snapshot.format,
            total_games=snapshot.total_games_analyzed,
            set_mechanics=set_mechanics,
            trophy_stats_section=trophy_stats_section,
            tempo_ratio=tempo_ratio,
            speed_label=speed_label,
            aggro_advantage=aggro_advantage,
            low_cmc_wr=low_cmc_wr,
            high_cmc_wr=high_cmc_wr,
            conflicts=conflicts,
            splash_label=splash_label,
            dual_land_count=dual_land_count,
            dual_land_alsa=dual_land_alsa,
            fixer_wr_premium=fixer_wr_premium,
            color_details=color_details,
            archetype_details=archetype_details,
        )

    def build_format_characteristics_prompt(self, snapshot: MetaSnapshot) -> str:
        """Build format characteristics prompt (section 1 only).

        This generates the "📋 포맷 특성" section independently to avoid
        token truncation issues. No color analysis - that's in COLOR_STRATEGY.
        """
        # Format speed data (with defaults for missing data)
        fs = snapshot.format_speed
        tempo_ratio = fs.tempo_ratio if fs else 1.0
        speed_label = fs.speed_label if fs else "보통"
        aggro_advantage = fs.aggro_advantage if fs else 0.0
        low_cmc_wr = fs.low_cmc_wr if fs else 0.5
        high_cmc_wr = fs.high_cmc_wr if fs else 0.5
        conflicts = ", ".join(fs.conflicts) if fs and fs.conflicts else "없음"

        # Splash indicator data (with defaults)
        si = snapshot.splash_indicator
        splash_label = si.splash_label if si else "보통"
        dual_land_count = si.dual_land_count if si else 0
        dual_land_alsa = si.dual_land_alsa if si else 7.0
        fixer_wr_premium = si.fixer_wr_premium if si else 0.0

        # Format archetype rankings for meta summary
        archetype_rankings = "\n".join(
            f"{i+1}. **{a.guild_name}** ({a.colors}) - "
            f"WR: {a.win_rate:.2%}, Share: {a.meta_share:.1%}"
            for i, a in enumerate(snapshot.top_archetypes[:10])
        )

        # Get set mechanics if available
        set_mechanics = get_set_mechanics(snapshot.expansion)

        # Calculate keyword distribution for LLM context
        # Import here to avoid circular import
        from src.analysis.color_meta import aggregate_keyword_distribution

        mechanic_names = get_mechanic_names(snapshot.expansion)
        keyword_dist = aggregate_keyword_distribution(snapshot.all_cards)
        keyword_distribution_str = keyword_dist.format_for_llm(mechanic_names)

        return self.format_characteristics_template.format(
            expansion=snapshot.expansion,
            format=snapshot.format,
            total_games=snapshot.total_games_analyzed,
            set_mechanics=set_mechanics,
            archetype_rankings=archetype_rankings,
            tempo_ratio=tempo_ratio,
            speed_label=speed_label,
            aggro_advantage=aggro_advantage,
            low_cmc_wr=low_cmc_wr,
            high_cmc_wr=high_cmc_wr,
            conflicts=conflicts,
            splash_label=splash_label,
            dual_land_count=dual_land_count,
            dual_land_alsa=dual_land_alsa,
            fixer_wr_premium=fixer_wr_premium,
            keyword_distribution=keyword_distribution_str,
        )

    def build_archetype_deep_dive_prompt(self, snapshot: MetaSnapshot) -> str:
        """Build archetype deep dive prompt (section 2 only).

        This generates the "🏆 상위 아키타입 심층 분석" section independently
        to avoid token truncation issues.
        """
        # Format detailed archetype data
        archetype_details = self._format_archetype_details(snapshot.top_archetypes[:5])

        # Get set mechanics if available
        set_mechanics = get_set_mechanics(snapshot.expansion)

        # Format trophy stats section if available
        trophy_stats_section = self._format_trophy_stats(snapshot.trophy_stats)

        return self.archetype_deep_dive_template.format(
            expansion=snapshot.expansion,
            format=snapshot.format,
            total_games=snapshot.total_games_analyzed,
            set_mechanics=set_mechanics,
            archetype_details=archetype_details,
            trophy_stats_section=trophy_stats_section,
        )

    def _format_color_details(self, colors: list) -> str:
        """Format detailed color analysis with bomb_factor, depth, and top cards."""
        lines = []
        for cs in colors:
            top_commons = ", ".join(cs.top_commons[:3]) if cs.top_commons else "N/A"
            top_uncommons = ", ".join(cs.top_uncommons[:3]) if cs.top_uncommons else "N/A"
            lines.append(f"""### {cs.color} (Rank #{cs.rank})
- 강도 점수: {cs.strength_score:.1f}
- 플레이어블: {cs.playable_count}장
- 폭탄 강도: {cs.bomb_factor:.2f}
- 카드 풀 깊이: {cs.depth_factor:.2f}
- 상위 커먼: {top_commons}
- 상위 언커먼: {top_uncommons}""")
        return "\n\n".join(lines) if lines else "색상 데이터 없음"

    def _format_trophy_stats(self, trophy_stats) -> str:
        """Format trophy deck statistics for LLM prompt with expanded analysis."""
        if not trophy_stats:
            return ""

        lines = ["## 🏆 Trophy Deck 분석 (7승 덱 통계)"]
        lines.append(f"- 총 Trophy Decks: {trophy_stats.total_trophy_decks}개")
        lines.append(f"- 분석된 덱: {trophy_stats.analyzed_decks}개")

        # Archetype trophy ranking with expanded stats
        lines.append("\n### 아키타입별 Trophy 분포 + 덱 특성")
        for arch in trophy_stats.get_archetype_ranking()[:5]:
            share = trophy_stats.get_archetype_share(arch.colors)

            # Build stats string with CMC, creature ratio, splash rate
            stats_parts = []
            if hasattr(arch, 'avg_cmc') and arch.avg_cmc:
                stats_parts.append(f"CMC {arch.avg_cmc:.1f}")
            if hasattr(arch, 'creature_ratio') and arch.creature_ratio:
                stats_parts.append(f"생물 {arch.creature_ratio * 100:.0f}%")
            if hasattr(arch, 'splash_rate') and arch.splash_rate:
                stats_parts.append(f"스플래시 {arch.splash_rate * 100:.0f}%")
            stats_str = " | ".join(stats_parts) if stats_parts else ""

            # Get top cards (basic lands excluded)
            if hasattr(arch, 'top_cards_nonland'):
                top_cards = ", ".join([c["name"] for c in arch.top_cards_nonland(3)])
            else:
                top_cards = ", ".join([c for c, _ in arch.top_cards(3)])

            lines.append(
                f"- **{arch.guild_name} ({arch.colors})**: "
                f"{arch.trophy_count}개 ({share:.1%})"
            )
            if stats_str:
                lines.append(f"  {stats_str}")
            lines.append(f"  핵심: {top_cards}")

        # Uncommon/Common key cards per archetype (crucial for draft priority)
        lines.append("\n### 7승 덱 핵심 Uncommon/Common (드래프트 우선순위)")
        for arch in trophy_stats.get_archetype_ranking()[:3]:
            if hasattr(arch, 'top_cards_by_rarity'):
                uc_cards = arch.top_cards_by_rarity('uncommon', n=3)
                cc_cards = arch.top_cards_by_rarity('common', n=3)
                uc_str = ", ".join([c["name"] for c in uc_cards]) if uc_cards else "N/A"
                cc_str = ", ".join([c["name"] for c in cc_cards]) if cc_cards else "N/A"
                lines.append(f"- **{arch.guild_name}**: U:{uc_str} / C:{cc_str}")

        # Overall top cards in trophy decks
        lines.append("\n### Trophy Deck 핵심 카드 (전체)")
        top_overall = trophy_stats.get_top_cards_overall(10)
        if top_overall:
            card_list = ", ".join([f"{name}({count})" for name, count in top_overall])
            lines.append(f"- {card_list}")

        return "\n".join(lines)

    def _format_archetype_details(self, archetypes: list) -> str:
        """Format detailed archetype analysis with synergy and key cards."""
        lines = []
        for a in archetypes:
            key_commons = ", ".join(a.key_commons[:3]) if a.key_commons else "N/A"
            bombs = ", ".join(a.bombs[:3]) if a.bombs else "N/A"
            trap_cards = ", ".join(a.trap_cards[:3]) if a.trap_cards else "N/A"
            synergy_cards = ", ".join(a.synergy_cards[:3]) if a.synergy_cards else "N/A"
            signpost = a.signpost_uncommon or "N/A"

            # Format splash variant data
            variant_info = "없음"
            if hasattr(a, 'variants') and a.variants:
                variant_lines = []
                for v in a.variants[:3]:  # Top 3 splash variants
                    delta = f"+{v.win_rate_delta*100:.1f}" if v.win_rate_delta > 0 else f"{v.win_rate_delta*100:.1f}"
                    variant_lines.append(f"+{v.added_color}: {v.win_rate:.1%} ({delta}%p)")
                variant_info = ", ".join(variant_lines)

            lines.append(f"""### {a.guild_name} ({a.colors}) - Rank #{a.rank}
**⚠️ 이 아키타입 고유 전략** (다른 아키타입과 다름)
- 승률: {a.win_rate:.2%}
- 메타 점유율: {a.meta_share:.1%}
- 시너지 리프트: {a.synergy_lift:.2%} (표준편차: {a.synergy_std:.3f})
- 스플래시 옵션: {variant_info}
- Signpost: {signpost}
- 핵심 커먼: {key_commons}
- 시너지 카드 (이 아키타입 전용): {synergy_cards}
- 폭탄: {bombs}
- 이 아키타입 트랩: {trap_cards}""")
        return "\n\n".join(lines) if lines else "아키타입 데이터 없음"

    def _format_sleeper_details(self, cards: list) -> str:
        """Format detailed sleeper card data with oracle text for LLM analysis."""
        if not cards:
            return "슬리퍼 카드 없음"

        lines = []
        for c in cards:
            # Get win rate safely
            gih_wr = c.stats.gih_wr if c.stats.gih_wr is not None else 0.0
            pick_rate = c.stats.pick_rate * 100  # Convert to percentage
            ata = c.stats.ata

            # Get best archetype win rate
            best_arch = c.best_archetype or "N/A"
            best_arch_wr = c.stats.archetype_wrs.get(best_arch, 0.0) if best_arch != "N/A" else 0.0

            # Oracle text (truncate if too long, but preserve full for analysis)
            oracle = c.oracle_text or "텍스트 없음"
            type_line = c.type_line or "타입 정보 없음"

            lines.append(f"""### {c.name} ({c.colors}, {c.rarity.value})
- 타입: {type_line}
- 효과: {oracle}
- GIH WR: {gih_wr:.2%}
- Pick Rate: {pick_rate:.1f}%
- ATA (Average Taken At): {ata:.1f}
- Z-score: +{c.irregularity_z:.2f} (저평가 정도)
- Best Archetype: {best_arch} ({best_arch_wr:.2%})
- Off-Archetype Penalty: {c.off_archetype_penalty:.2%}""")
        return "\n\n".join(lines)

    def _format_trap_details(self, cards: list) -> str:
        """Format detailed trap card data with oracle text for LLM analysis."""
        if not cards:
            return "트랩 카드 없음"

        lines = []
        for c in cards:
            # Get win rate safely
            gih_wr = c.stats.gih_wr if c.stats.gih_wr is not None else 0.0
            pick_rate = c.stats.pick_rate * 100  # Convert to percentage
            ata = c.stats.ata

            # Get best archetype win rate
            best_arch = c.best_archetype or "N/A"
            best_arch_wr = c.stats.archetype_wrs.get(best_arch, 0.0) if best_arch != "N/A" else 0.0

            # Oracle text
            oracle = c.oracle_text or "텍스트 없음"
            type_line = c.type_line or "타입 정보 없음"

            lines.append(f"""### {c.name} ({c.colors}, {c.rarity.value})
- 타입: {type_line}
- 효과: {oracle}
- GIH WR: {gih_wr:.2%}
- Pick Rate: {pick_rate:.1f}% (높으면 과대평가)
- ATA (Average Taken At): {ata:.1f} (낮으면 일찍 픽됨 = 과대평가)
- Z-score: {c.irregularity_z:.2f} (과대평가 정도)
- Best Archetype: {best_arch} ({best_arch_wr:.2%})
- Off-Archetype Penalty: {c.off_archetype_penalty:.2%}""")
        return "\n\n".join(lines)


def build_meta_prompt(snapshot: MetaSnapshot) -> str:
    """Convenience function to build meta prompt."""
    builder = PromptBuilder()
    return builder.build_meta_prompt(snapshot)


def build_card_prompt(card: Card) -> str:
    """Convenience function to build card prompt."""
    builder = PromptBuilder()
    return builder.build_card_prompt(card)


def build_format_overview_prompt(snapshot: MetaSnapshot) -> str:
    """Convenience function to build format overview prompt."""
    builder = PromptBuilder()
    return builder.build_format_overview_prompt(snapshot)


def build_format_characteristics_prompt(snapshot: MetaSnapshot) -> str:
    """Convenience function to build format characteristics prompt."""
    builder = PromptBuilder()
    return builder.build_format_characteristics_prompt(snapshot)


def build_archetype_deep_dive_prompt(snapshot: MetaSnapshot) -> str:
    """Convenience function to build archetype deep dive prompt."""
    builder = PromptBuilder()
    return builder.build_archetype_deep_dive_prompt(snapshot)


def build_color_strategy_prompt(snapshot: MetaSnapshot) -> str:
    """Convenience function to build color strategy prompt."""
    builder = PromptBuilder()
    return builder.build_color_strategy_prompt(snapshot)
