"""Contract validation tests."""

import pytest

from src.contracts import (
    LoaderContract,
    ScorerContract,
    IrregularityContract,
    ReportContract,
    LLMContract,
)
from src.models.card import CardStats, Rarity
from src.data.loader import SeventeenLandsLoader
from src.scoring.card_scorer import CardScorer
from src.scoring.irregularity import IrregularityDetector
from src.report.markdown_gen import MarkdownReportGenerator


class TestLoaderContract:
    """Test DataLoader contract compliance."""

    def test_loader_has_required_methods(self):
        contract = LoaderContract()
        loader = SeventeenLandsLoader()

        is_valid, errors = contract.validate(loader)
        assert is_valid, f"Contract validation failed: {errors}"

    def test_loader_methods_are_callable(self):
        loader = SeventeenLandsLoader()

        assert callable(getattr(loader, "fetch_card_ratings"))
        assert callable(getattr(loader, "fetch_color_ratings"))


class TestScorerContract:
    """Test CardScorer contract compliance."""

    def test_scorer_has_required_methods(self):
        contract = ScorerContract()
        scorer = CardScorer()

        is_valid, errors = contract.validate(scorer)
        assert is_valid, f"Contract validation failed: {errors}"

    def test_scorer_output_range(self):
        contract = ScorerContract()
        scorer = CardScorer()

        # Test with mock data
        test_card = CardStats(
            name="Test Card",
            colors="W",
            rarity=Rarity.COMMON,
            gih_wr=0.55,
            gih_games=1000,
            gih_wins=550,
            alsa=7.0,
        )

        all_cards = [test_card] + [
            CardStats(
                name=f"Card {i}",
                colors="U",
                rarity=Rarity.COMMON,
                gih_wr=0.50 + (i * 0.01),
                gih_games=1000,
                gih_wins=int(1000 * (0.50 + i * 0.01)),
                alsa=7.0,
            )
            for i in range(20)
        ]

        score = scorer.calculate_composite_score(test_card, all_cards)

        is_valid, error = contract.validate_output(score)
        assert is_valid, f"Output validation failed: {error}"


class TestIrregularityContract:
    """Test IrregularityDetector contract compliance."""

    def test_detector_has_required_methods(self):
        contract = IrregularityContract()
        detector = IrregularityDetector()

        is_valid, errors = contract.validate(detector)
        assert is_valid, f"Contract validation failed: {errors}"

    def test_detector_output_categories(self):
        contract = IrregularityContract()

        # Test valid outputs
        for category in ["sleeper", "trap", "normal"]:
            is_valid, error = contract.validate_output(category, 1.5)
            assert is_valid, f"Category {category} should be valid"

        # Test invalid category
        is_valid, error = contract.validate_output("invalid", 1.5)
        assert not is_valid


class TestReportContract:
    """Test ReportGenerator contract compliance."""

    def test_report_gen_has_required_methods(self):
        # Note: MarkdownReportGenerator has generate_markdown but not export_json
        # export_json is in json_export module separately
        generator = MarkdownReportGenerator()

        assert hasattr(generator, "generate_markdown")
        assert callable(getattr(generator, "generate_markdown"))


class TestEdgeCases:
    """Test edge cases for scoring."""

    def test_scorer_empty_games(self):
        """Test scorer handles cards with no games."""
        scorer = CardScorer()

        zero_games_card = CardStats(
            name="No Games",
            colors="B",
            rarity=Rarity.COMMON,
            gih_wr=0.0,
            gih_games=0,
            gih_wins=0,
        )

        all_cards = [zero_games_card] + [
            CardStats(
                name=f"Card {i}",
                colors="R",
                rarity=Rarity.COMMON,
                gih_wr=0.50,
                gih_games=1000,
                gih_wins=500,
            )
            for i in range(20)
        ]

        # Should not raise and should return valid score
        score = scorer.calculate_composite_score(zero_games_card, all_cards)
        assert 0 <= score <= 100

    def test_scorer_extreme_winrate(self):
        """Test scorer handles extreme win rates."""
        scorer = CardScorer()

        extreme_card = CardStats(
            name="Extreme",
            colors="G",
            rarity="mythic",
            gih_wr=1.0,
            gih_games=10,
            gih_wins=10,
        )

        all_cards = [extreme_card] + [
            CardStats(
                name=f"Card {i}",
                colors="W",
                rarity="common",
                gih_wr=0.50,
                gih_games=1000,
                gih_wins=500,
            )
            for i in range(20)
        ]

        score = scorer.calculate_composite_score(extreme_card, all_cards)
        assert 0 <= score <= 100

    def test_scorer_large_sample(self):
        """Test scorer handles large sample sizes."""
        scorer = CardScorer()

        large_sample_card = CardStats(
            name="Large Sample",
            colors="U",
            rarity="common",
            gih_wr=0.60,
            gih_games=100000,
            gih_wins=60000,
        )

        all_cards = [large_sample_card] + [
            CardStats(
                name=f"Card {i}",
                colors="B",
                rarity="common",
                gih_wr=0.50,
                gih_games=1000,
                gih_wins=500,
            )
            for i in range(20)
        ]

        score = scorer.calculate_composite_score(large_sample_card, all_cards)
        assert 0 <= score <= 100
        # Large sample with 60% WR should score high
        assert score > 50
