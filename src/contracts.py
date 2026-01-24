"""Interface contracts for module integration and validation.

Contracts define the expected input/output types and required methods
for each module, enabling parallel development and automatic verification.
"""

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


# Forward type references (actual types defined in models/)
@dataclass
class CardStats:
    """Minimal card stats for contract validation."""
    name: str = ""
    gih_wr: float = 0.0
    gih_games: int = 0
    gih_wins: int = 0
    gns_wr: float = 0.0
    alsa: float = 7.0
    ata: float = 7.0
    oh_wr: float = 0.0
    gd_wr: float = 0.0
    pick_rate: float = 0.0


# ============================================================================
# Protocol Definitions (Duck Typing Interfaces)
# ============================================================================


@runtime_checkable
class DataLoaderProtocol(Protocol):
    """Protocol for data loading implementations."""

    def fetch_card_ratings(
        self, expansion: str, format: str = "PremierDraft"
    ) -> list[dict]:
        """Fetch card ratings from 17lands API."""
        ...

    def fetch_color_ratings(
        self, expansion: str, format: str = "PremierDraft"
    ) -> list[dict]:
        """Fetch color/archetype ratings from 17lands API."""
        ...


@runtime_checkable
class CardScorerProtocol(Protocol):
    """Protocol for card scoring implementations."""

    def calculate_composite_score(self, card: CardStats, all_cards: list[CardStats]) -> float:
        """Calculate composite score (0-100) for a card."""
        ...

    def assign_grade(self, score: float) -> str:
        """Assign letter grade based on score."""
        ...


@runtime_checkable
class ColorScorerProtocol(Protocol):
    """Protocol for color strength scoring implementations."""

    def calculate_color_strength(
        self, color: str, cards: list, config: dict
    ) -> float:
        """Calculate strength score for a color."""
        ...


@runtime_checkable
class IrregularityDetectorProtocol(Protocol):
    """Protocol for sleeper/trap detection implementations."""

    def detect_irregularity(
        self, card: CardStats, all_cards: list[CardStats]
    ) -> tuple[str, float]:
        """
        Detect if card is sleeper, trap, or normal.

        Returns:
            tuple[str, float]: (category, z_score)
            - category: "sleeper", "trap", or "normal"
            - z_score: deviation z-score
        """
        ...


@runtime_checkable
class ReportGeneratorProtocol(Protocol):
    """Protocol for report generation implementations."""

    def generate_markdown(self, snapshot: dict, config: dict) -> str:
        """Generate markdown report from meta snapshot."""
        ...

    def export_json(self, snapshot: dict, filepath: str) -> None:
        """Export meta snapshot to JSON file."""
        ...


@runtime_checkable
class LLMClientProtocol(Protocol):
    """Protocol for LLM client implementations."""

    def analyze_meta(self, meta_data: dict, prompt_template: str) -> str:
        """Generate LLM analysis of meta data."""
        ...

    def analyze_card(self, card_data: dict, prompt_template: str) -> str:
        """Generate LLM analysis of specific card."""
        ...


# ============================================================================
# Contract Dataclasses (For Testing & Validation)
# ============================================================================


@dataclass
class LoaderContract:
    """Contract specification for DataLoader implementations."""

    output_type: type = list
    required_methods: list[str] = field(
        default_factory=lambda: [
            "fetch_card_ratings",
            "fetch_color_ratings",
        ]
    )

    def validate(self, instance: object) -> tuple[bool, list[str]]:
        """Validate that instance fulfills the contract."""
        errors = []

        for method in self.required_methods:
            if not hasattr(instance, method):
                errors.append(f"Missing required method: {method}")
            elif not callable(getattr(instance, method)):
                errors.append(f"Method {method} is not callable")

        return len(errors) == 0, errors


@dataclass
class ScorerContract:
    """Contract specification for CardScorer implementations."""

    input_type: type = CardStats
    output_type: type = float
    output_range: tuple[float, float] = (0.0, 100.0)
    required_methods: list[str] = field(
        default_factory=lambda: [
            "calculate_composite_score",
            "assign_grade",
        ]
    )

    def validate(self, instance: object) -> tuple[bool, list[str]]:
        """Validate that instance fulfills the contract."""
        errors = []

        for method in self.required_methods:
            if not hasattr(instance, method):
                errors.append(f"Missing required method: {method}")

        return len(errors) == 0, errors

    def validate_output(self, score: float) -> tuple[bool, str]:
        """Validate that output is within expected range."""
        min_val, max_val = self.output_range
        if not (min_val <= score <= max_val):
            return False, f"Score {score} outside range [{min_val}, {max_val}]"
        return True, ""


@dataclass
class IrregularityContract:
    """Contract specification for Irregularity detection."""

    output_categories: list[str] = field(
        default_factory=lambda: ["sleeper", "trap", "normal"]
    )
    required_methods: list[str] = field(
        default_factory=lambda: ["detect_irregularity"]
    )

    def validate(self, instance: object) -> tuple[bool, list[str]]:
        """Validate that instance fulfills the contract."""
        errors = []

        for method in self.required_methods:
            if not hasattr(instance, method):
                errors.append(f"Missing required method: {method}")

        return len(errors) == 0, errors

    def validate_output(self, category: str, z_score: float) -> tuple[bool, str]:
        """Validate irregularity detection output."""
        if category not in self.output_categories:
            return False, f"Invalid category: {category}"
        if not isinstance(z_score, (int, float)):
            return False, f"Z-score must be numeric, got {type(z_score)}"
        return True, ""


@dataclass
class ReportContract:
    """Contract specification for Report generation."""

    output_type: type = str
    required_methods: list[str] = field(
        default_factory=lambda: [
            "generate_markdown",
            "export_json",
        ]
    )

    def validate(self, instance: object) -> tuple[bool, list[str]]:
        """Validate that instance fulfills the contract."""
        errors = []

        for method in self.required_methods:
            if not hasattr(instance, method):
                errors.append(f"Missing required method: {method}")

        return len(errors) == 0, errors


@dataclass
class LLMContract:
    """Contract specification for LLM client implementations."""

    output_type: type = str
    required_methods: list[str] = field(
        default_factory=lambda: [
            "analyze_meta",
            "analyze_card",
        ]
    )

    def validate(self, instance: object) -> tuple[bool, list[str]]:
        """Validate that instance fulfills the contract."""
        errors = []

        for method in self.required_methods:
            if not hasattr(instance, method):
                errors.append(f"Missing required method: {method}")

        return len(errors) == 0, errors


# ============================================================================
# Contract Registry
# ============================================================================


CONTRACTS = {
    "loader": LoaderContract(),
    "scorer": ScorerContract(),
    "irregularity": IrregularityContract(),
    "report": ReportContract(),
    "llm": LLMContract(),
}


def validate_all_contracts(modules: dict[str, object]) -> dict[str, tuple[bool, list[str]]]:
    """
    Validate all modules against their contracts.

    Args:
        modules: Dict mapping contract name to module instance

    Returns:
        Dict mapping contract name to (is_valid, errors) tuple
    """
    results = {}

    for name, instance in modules.items():
        if name in CONTRACTS:
            contract = CONTRACTS[name]
            is_valid, errors = contract.validate(instance)
            results[name] = (is_valid, errors)
        else:
            results[name] = (False, [f"Unknown contract: {name}"])

    return results
