"""Gemini API client for LLM analysis."""

import logging
import os
from typing import Optional

from google import genai
from google.genai import types
from dotenv import load_dotenv

from src.llm.prompt_builder import PromptBuilder
from src.models.card import Card
from src.models.meta import MetaSnapshot

logger = logging.getLogger(__name__)


class GeminiClient:
    """Client for Google Gemini API."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-3-flash-preview",
        max_tokens: int = 8192,
        temperature: float = 1.0,
    ):
        """
        Initialize Gemini client.

        Args:
            api_key: Gemini API key (defaults to GEMINI_API_KEY env var)
            model: Model to use
            max_tokens: Maximum response tokens (increased from 4096 to 8192)
            temperature: Sampling temperature (Gemini 3 recommends 1.0)
        """
        load_dotenv()

        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            logger.warning(
                "No Gemini API key found. LLM analysis will be disabled."
            )
            self.enabled = False
            return

        self.enabled = True
        self.model_name = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        # Configure API client (Gemini 3 style)
        self.client = genai.Client(api_key=self.api_key)
        self.prompt_builder = PromptBuilder()

    def _generate(self, prompt: str) -> Optional[str]:
        """
        Generate response from Gemini.

        Args:
            prompt: Input prompt

        Returns:
            Generated text or None on failure
        """
        if not self.enabled:
            logger.warning("Gemini client is disabled (no API key)")
            return None

        try:
            config = types.GenerateContentConfig(
                max_output_tokens=self.max_tokens,
                temperature=self.temperature,
            )

            response = self.client.models.generate_content(
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            if response and response.text:
                return response.text
            else:
                logger.warning("Empty response from Gemini")
                return None

        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            return None

    def analyze_meta(self, snapshot: MetaSnapshot) -> Optional[str]:
        """
        Generate meta analysis for a snapshot.

        DEPRECATED: Use generate_color_strategy() instead.

        Args:
            snapshot: MetaSnapshot to analyze

        Returns:
            Analysis text or None
        """
        prompt = self.prompt_builder.build_meta_prompt(snapshot)
        logger.info(f"Generating meta analysis for {snapshot.expansion}")

        return self._generate(prompt)

    def generate_color_strategy(self, snapshot: MetaSnapshot) -> Optional[str]:
        """
        Generate color strategy analysis (replaces analyze_meta).

        This produces detailed analysis for all 5 colors with:
        - Strengths and weaknesses
        - Top 3 commons per color
        - P1P1 color priority

        Args:
            snapshot: MetaSnapshot to analyze

        Returns:
            Color strategy analysis text or None
        """
        prompt = self.prompt_builder.build_color_strategy_prompt(snapshot)
        logger.info(f"Generating color strategy for {snapshot.expansion}")

        return self._generate(prompt)

    def analyze_card(self, card: Card) -> Optional[str]:
        """
        Generate card-specific analysis.

        Args:
            card: Card to analyze

        Returns:
            Analysis text or None
        """
        prompt = self.prompt_builder.build_card_prompt(card)
        logger.info(f"Generating card analysis for {card.name}")

        return self._generate(prompt)

    def get_strategy_tips(self, snapshot: MetaSnapshot) -> Optional[str]:
        """
        Generate strategic tips for a format.

        Args:
            snapshot: MetaSnapshot to analyze

        Returns:
            Strategy tips text or None
        """
        prompt = self.prompt_builder.build_strategy_prompt(snapshot)
        logger.info(f"Generating strategy tips for {snapshot.expansion}")

        return self._generate(prompt)

    def generate_format_overview(self, snapshot: MetaSnapshot) -> Optional[str]:
        """
        Generate comprehensive format overview analysis.

        This produces a detailed 7-section analysis covering:
        - Format summary
        - Speed analysis
        - Color insights
        - Archetype guide
        - Splash guide
        - Sleeper & trap analysis
        - Draft strategy tips

        Args:
            snapshot: MetaSnapshot to analyze

        Returns:
            Comprehensive format overview text or None
        """
        prompt = self.prompt_builder.build_format_overview_prompt(snapshot)
        logger.info(f"Generating format overview for {snapshot.expansion}")

        return self._generate(prompt)

    def generate_format_characteristics(self, snapshot: MetaSnapshot) -> Optional[str]:
        """
        Generate format characteristics analysis (section 1 only).

        This produces the "📋 포맷 특성" section independently to avoid
        token truncation issues.

        Args:
            snapshot: MetaSnapshot to analyze

        Returns:
            Format characteristics text or None
        """
        prompt = self.prompt_builder.build_format_characteristics_prompt(snapshot)
        logger.info(f"Generating format characteristics for {snapshot.expansion}")

        return self._generate(prompt)

    def generate_archetype_deep_dive(self, snapshot: MetaSnapshot) -> Optional[str]:
        """
        Generate archetype deep dive analysis (section 2 only).

        This produces the "🏆 상위 아키타입 심층 분석" section independently
        to avoid token truncation issues.

        Args:
            snapshot: MetaSnapshot to analyze

        Returns:
            Archetype deep dive text or None
        """
        prompt = self.prompt_builder.build_archetype_deep_dive_prompt(snapshot)
        logger.info(f"Generating archetype deep dive for {snapshot.expansion}")

        return self._generate(prompt)

    def _parse_format_overview_sections(self, text: str) -> tuple[Optional[str], Optional[str]]:
        """
        Parse format_overview into two sections.

        Returns:
            Tuple of (format_characteristics, archetype_deep_dive)
        """
        if not text:
            return None, None

        format_characteristics = None
        archetype_deep_dive = None

        # Split by section headers
        lines = text.split('\n')
        current_section = None
        section_lines = {"format": [], "archetype": []}

        for line in lines:
            # Detect section headers
            if '📋' in line or ('1.' in line and '포맷' in line):
                current_section = "format"
                section_lines["format"].append(line)
            elif '🏆' in line or ('2.' in line and '아키타입' in line):
                current_section = "archetype"
                section_lines["archetype"].append(line)
            elif current_section:
                section_lines[current_section].append(line)

        if section_lines["format"]:
            format_characteristics = '\n'.join(section_lines["format"]).strip()
        if section_lines["archetype"]:
            archetype_deep_dive = '\n'.join(section_lines["archetype"]).strip()

        return format_characteristics, archetype_deep_dive

    def enrich_snapshot(
        self,
        snapshot: MetaSnapshot,
        include_color_strategy: bool = True,
        include_strategy: bool = True,
        include_format_overview: bool = True,
        use_split_api: bool = True,
        include_meta: bool = False,  # DEPRECATED: kept for backwards compatibility
    ) -> MetaSnapshot:
        """
        Enrich snapshot with LLM analysis.

        Args:
            snapshot: MetaSnapshot to enrich
            include_color_strategy: Whether to include color strategy analysis (5 colors + P1P1)
            include_strategy: Whether to include strategy tips
            include_format_overview: Whether to include format overview
            use_split_api: Whether to use split API calls for format overview
                           (recommended to avoid token truncation)
            include_meta: DEPRECATED - use include_color_strategy instead

        Returns:
            Enriched snapshot
        """
        if not self.enabled:
            logger.warning("Skipping LLM enrichment (client disabled)")
            return snapshot

        # Color strategy analysis (replaces meta_analysis)
        if include_color_strategy:
            snapshot.llm_color_strategy = self.generate_color_strategy(snapshot)

        # DEPRECATED: backwards compatibility
        if include_meta:
            snapshot.llm_meta_analysis = self.analyze_meta(snapshot)

        if include_strategy:
            snapshot.llm_strategy_tips = self.get_strategy_tips(snapshot)

        if include_format_overview:
            if use_split_api:
                # Use split API calls to avoid token truncation
                logger.info("Using split API calls for format overview")
                format_char = self.generate_format_characteristics(snapshot)
                arch_deep = self.generate_archetype_deep_dive(snapshot)
                snapshot.llm_format_characteristics = format_char
                snapshot.llm_archetype_deep_dive = arch_deep
                # Combine for backwards compatibility
                if format_char and arch_deep:
                    snapshot.llm_format_overview = f"{format_char}\n\n{arch_deep}"
                elif format_char:
                    snapshot.llm_format_overview = format_char
                elif arch_deep:
                    snapshot.llm_format_overview = arch_deep
            else:
                # Legacy single API call
                overview = self.generate_format_overview(snapshot)
                snapshot.llm_format_overview = overview
                # Parse into separate sections
                format_char, arch_deep = self._parse_format_overview_sections(overview)
                snapshot.llm_format_characteristics = format_char
                snapshot.llm_archetype_deep_dive = arch_deep

        return snapshot
