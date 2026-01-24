"""Percentile-based threshold calibration.

Calibrates thresholds based on actual data distribution rather than
hardcoded values.
"""

import logging
import statistics
from dataclasses import dataclass
from typing import Optional

from src.models.card import Card, CardStats
from src.models.meta import ThresholdConfig

logger = logging.getLogger(__name__)


def percentile(values: list[float], p: float) -> float:
    """
    Calculate percentile of a list of values.

    Args:
        values: List of numeric values
        p: Percentile (0-100)

    Returns:
        Value at the given percentile
    """
    if not values:
        return 0.0

    sorted_values = sorted(values)
    n = len(sorted_values)
    k = (n - 1) * (p / 100)
    f = int(k)
    c = f + 1

    if f >= n - 1:
        return sorted_values[-1]

    return sorted_values[f] + (k - f) * (sorted_values[c] - sorted_values[f])


@dataclass
class CalibrationStats:
    """Statistics collected during calibration."""

    # Distribution metrics
    gih_wr_mean: float = 0.0
    gih_wr_std: float = 0.0
    gih_wr_median: float = 0.0

    variance_mean: float = 0.0
    variance_std: float = 0.0
    variance_median: float = 0.0

    deviation_mean: float = 0.0
    deviation_std: float = 0.0

    # Counts
    total_cards: int = 0
    cards_with_variance: int = 0

    # Percentile values
    gih_wr_p95: float = 0.0
    gih_wr_p50: float = 0.0
    variance_p75: float = 0.0
    deviation_p90: float = 0.0
    deviation_p10: float = 0.0


class Calibrator:
    """Calibrates scoring thresholds from data distribution."""

    def __init__(self, config: Optional[dict] = None):
        """
        Initialize calibrator.

        Args:
            config: Calibration config with percentile settings
        """
        self.config = config or {
            "synergy_percentile": 75,
            "sleeper_percentile": 90,
            "trap_percentile": 10,
            "bomb_percentile": 95,
            "playable_percentile": 35,  # 50 → 35: 상위 65% 카드를 playable로 분류
        }
        self.stats: Optional[CalibrationStats] = None

    def calibrate(self, cards: list[CardStats]) -> ThresholdConfig:
        """
        Calculate thresholds from card data distribution.

        Args:
            cards: List of CardStats to analyze

        Returns:
            ThresholdConfig with calibrated values
        """
        if not cards:
            logger.warning("No cards provided for calibration, using defaults")
            return ThresholdConfig()

        # Filter cards with sufficient data
        valid_cards = [c for c in cards if c.gih_games >= 200]

        if len(valid_cards) < 50:
            logger.warning(
                f"Only {len(valid_cards)} cards with sufficient data, "
                "calibration may be unreliable"
            )

        # Collect GIH WR distribution
        gih_wrs = [c.gih_wr for c in valid_cards if c.gih_wr > 0]

        if not gih_wrs:
            logger.error("No valid GIH WR data for calibration")
            return ThresholdConfig()

        # Calculate GIH WR statistics
        gih_mean = statistics.mean(gih_wrs)
        gih_std = statistics.stdev(gih_wrs) if len(gih_wrs) > 1 else 0.05
        gih_median = statistics.median(gih_wrs)

        # Calculate variance distribution (if archetype data available)
        variances = []
        for card in valid_cards:
            if card.archetype_wrs and len(card.archetype_wrs) >= 3:
                card_variance = statistics.variance(card.archetype_wrs.values())
                variances.append(card_variance)

        # Calculate raw deviations from expected WR
        # NOTE: We store raw deviations, not Z-scores, to avoid double normalization
        # The percentile of deviations gives us threshold values directly
        deviations = []
        for card in valid_cards:
            expected_wr = 0.50 + (card.pick_rate * 0.12) - (card.alsa - 7) * 0.01
            deviation = card.gih_wr - expected_wr
            deviations.append(deviation)

        # Build calibration stats
        self.stats = CalibrationStats(
            gih_wr_mean=gih_mean,
            gih_wr_std=gih_std,
            gih_wr_median=gih_median,
            variance_mean=statistics.mean(variances) if variances else 0.0,
            variance_std=statistics.stdev(variances) if len(variances) > 1 else 0.0,
            variance_median=statistics.median(variances) if variances else 0.0,
            deviation_mean=statistics.mean(deviations) if deviations else 0.0,
            deviation_std=statistics.stdev(deviations) if len(deviations) > 1 else 0.03,
            total_cards=len(valid_cards),
            cards_with_variance=len(variances),
            gih_wr_p95=percentile(gih_wrs, 95),
            gih_wr_p50=percentile(gih_wrs, 50),
            variance_p75=percentile(variances, 75) if variances else 0.002,
            deviation_p90=percentile(deviations, 90) if deviations else 0.03,
            deviation_p10=percentile(deviations, 10) if deviations else -0.03,
        )

        # Calculate thresholds from percentiles
        synergy_variance = (
            percentile(variances, self.config["synergy_percentile"])
            if variances
            else 0.002
        )

        # Calculate sleeper/trap thresholds as Z-scores from deviation distribution
        # This is consistent with how IrregularityDetector calculates Z-scores:
        # z = (deviation - mean(deviations)) / std(deviations)
        dev_mean = self.stats.deviation_mean
        dev_std = self.stats.deviation_std if self.stats.deviation_std > 0 else 0.03

        sleeper_deviation = (
            percentile(deviations, self.config["sleeper_percentile"])
            if deviations
            else 0.03
        )
        sleeper_z = (sleeper_deviation - dev_mean) / dev_std

        trap_deviation = (
            percentile(deviations, self.config["trap_percentile"])
            if deviations
            else -0.03
        )
        trap_z = (trap_deviation - dev_mean) / dev_std

        bomb_wr = percentile(gih_wrs, self.config["bomb_percentile"])
        playable_wr = percentile(gih_wrs, self.config["playable_percentile"])

        thresholds = ThresholdConfig(
            synergy_variance=synergy_variance,
            stable_variance=synergy_variance / 2,  # Half of synergy threshold
            sleeper_z=sleeper_z,
            trap_z=trap_z,
            bomb_wr=bomb_wr,
            playable_wr=playable_wr,
            min_games=200,
            calibration_percentiles=self.config,
        )

        logger.info(
            f"Calibration complete: "
            f"bomb_wr={bomb_wr:.3f}, "
            f"playable_wr={playable_wr:.3f}, "
            f"sleeper_z={sleeper_z:.2f}, "
            f"trap_z={trap_z:.2f}"
        )

        return thresholds

    def validate_calibration(
        self,
        cards: list[Card],
        known_sleepers: Optional[list[str]] = None,
        known_traps: Optional[list[str]] = None,
    ) -> dict:
        """
        Validate calibration against known sleeper/trap cards.

        Args:
            cards: Analyzed cards with irregularity_type set
            known_sleepers: List of known sleeper card names
            known_traps: List of known trap card names

        Returns:
            Validation metrics (precision, recall)
        """
        known_sleepers = known_sleepers or []
        known_traps = known_traps or []

        detected_sleepers = {c.name for c in cards if c.irregularity_type == "sleeper"}
        detected_traps = {c.name for c in cards if c.irregularity_type == "trap"}

        known_sleeper_set = set(known_sleepers)
        known_trap_set = set(known_traps)

        # Sleeper metrics
        sleeper_true_positives = len(detected_sleepers & known_sleeper_set)
        sleeper_precision = (
            sleeper_true_positives / len(detected_sleepers)
            if detected_sleepers
            else 0.0
        )
        sleeper_recall = (
            sleeper_true_positives / len(known_sleeper_set)
            if known_sleeper_set
            else 0.0
        )

        # Trap metrics
        trap_true_positives = len(detected_traps & known_trap_set)
        trap_precision = (
            trap_true_positives / len(detected_traps) if detected_traps else 0.0
        )
        trap_recall = (
            trap_true_positives / len(known_trap_set) if known_trap_set else 0.0
        )

        return {
            "sleeper": {
                "detected": len(detected_sleepers),
                "known": len(known_sleeper_set),
                "true_positives": sleeper_true_positives,
                "precision": sleeper_precision,
                "recall": sleeper_recall,
            },
            "trap": {
                "detected": len(detected_traps),
                "known": len(known_trap_set),
                "true_positives": trap_true_positives,
                "precision": trap_precision,
                "recall": trap_recall,
            },
        }

    def get_distribution_report(self) -> str:
        """Generate human-readable distribution report."""
        if not self.stats:
            return "No calibration data available. Run calibrate() first."

        return f"""
=== Calibration Distribution Report ===

GIH Win Rate Distribution:
  Mean:   {self.stats.gih_wr_mean:.4f}
  StdDev: {self.stats.gih_wr_std:.4f}
  Median: {self.stats.gih_wr_median:.4f}
  P95 (Bomb threshold):     {self.stats.gih_wr_p95:.4f}
  P50 (Playable threshold): {self.stats.gih_wr_p50:.4f}

Archetype Variance Distribution:
  Cards with variance data: {self.stats.cards_with_variance}
  Mean:   {self.stats.variance_mean:.6f}
  StdDev: {self.stats.variance_std:.6f}
  Median: {self.stats.variance_median:.6f}
  P75 (Synergy threshold):  {self.stats.variance_p75:.6f}

Deviation Distribution (Actual - Expected WR):
  Mean:   {self.stats.deviation_mean:.4f}
  StdDev: {self.stats.deviation_std:.4f}
  P90 (Sleeper deviation): {self.stats.deviation_p90:.4f}
  P10 (Trap deviation):    {self.stats.deviation_p10:.4f}

Sample Size: {self.stats.total_cards} cards
"""


def calibrate_thresholds(cards: list[CardStats], config: Optional[dict] = None) -> ThresholdConfig:
    """
    Convenience function to calibrate thresholds.

    Args:
        cards: List of CardStats
        config: Optional calibration config

    Returns:
        Calibrated ThresholdConfig
    """
    calibrator = Calibrator(config)
    return calibrator.calibrate(cards)
