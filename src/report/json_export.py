"""JSON export utilities."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.models.meta import MetaSnapshot


def export_json(
    snapshot: MetaSnapshot,
    output_dir: str = "output",
    include_all_cards: bool = False,
) -> str:
    """
    Export meta snapshot to JSON file.

    Args:
        snapshot: MetaSnapshot to export
        output_dir: Output directory
        include_all_cards: Whether to include all cards (can be large)

    Returns:
        Path to exported file
    """
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate filename
    timestamp = snapshot.timestamp.strftime("%Y-%m-%d")
    filename = f"{snapshot.expansion}_{snapshot.format}_{timestamp}_meta.json"
    filepath = output_path / filename

    # Build export data
    data = snapshot.to_dict()

    # Optionally add all cards (can be very large)
    if include_all_cards:
        data["all_cards"] = [c.to_dict() for c in snapshot.all_cards]

    # Write JSON
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    return str(filepath)


def export_summary_json(
    snapshot: MetaSnapshot,
    output_dir: str = "output",
) -> str:
    """
    Export compact summary JSON (no full card list).

    Args:
        snapshot: MetaSnapshot to export
        output_dir: Output directory

    Returns:
        Path to exported file
    """
    return export_json(snapshot, output_dir, include_all_cards=False)


def load_snapshot_json(filepath: str) -> dict[str, Any]:
    """
    Load meta snapshot from JSON file.

    Args:
        filepath: Path to JSON file

    Returns:
        Dict representation of snapshot
    """
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def merge_snapshots(
    *filepaths: str,
    output_dir: str = "output",
) -> str:
    """
    Merge multiple snapshot JSONs for comparison.

    Args:
        *filepaths: Paths to JSON files
        output_dir: Output directory

    Returns:
        Path to merged file
    """
    snapshots = [load_snapshot_json(fp) for fp in filepaths]

    merged = {
        "merge_timestamp": datetime.now().isoformat(),
        "snapshots": snapshots,
        "comparison": {
            "expansions": [s.get("meta", {}).get("expansion") for s in snapshots],
            "formats": [s.get("meta", {}).get("format") for s in snapshots],
        },
    }

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    filepath = output_path / f"merged_comparison_{timestamp}.json"

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2, ensure_ascii=False, default=str)

    return str(filepath)
