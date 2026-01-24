"""CLI interface for MTG Draft Analyzer."""

import logging
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.analysis.color_meta import MetaAnalyzer
from src.data.cache import CacheManager
from src.llm.gemini_client import GeminiClient
from src.report.html_gen import HtmlReportGenerator
from src.report.json_export import export_json
from src.report.markdown_gen import MarkdownReportGenerator

app = typer.Typer(
    name="draft-analyzer",
    help="MTG Draft Meta Analyzer - Analyze draft formats using 17lands data",
)
console = Console()


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


@app.command()
def analyze(
    expansion: str = typer.Argument(..., help="Set code (e.g., FDN, DSK, BLB)"),
    format: str = typer.Option(
        "PremierDraft",
        "--format", "-f",
        help="Draft format (PremierDraft, QuickDraft, TradDraft)",
    ),
    output_dir: str = typer.Option(
        "output",
        "--output", "-o",
        help="Output directory for reports",
    ),
    include_llm: bool = typer.Option(
        True,
        "--llm/--no-llm",
        help="Include LLM analysis (requires GEMINI_API_KEY)",
    ),
    generate_html: bool = typer.Option(
        False,
        "--html",
        help="Generate interactive HTML draft guide",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose", "-v",
        help="Enable verbose logging",
    ),
):
    """
    Analyze a draft format and generate reports.

    Example:
        draft-analyzer analyze FDN --format PremierDraft
    """
    setup_logging(verbose)

    console.print(f"\n[bold blue]MTG Draft Meta Analyzer[/bold blue]")
    console.print(f"Analyzing: [green]{expansion}[/green] {format}\n")

    # Initialize components
    cache = CacheManager()
    gemini = GeminiClient() if include_llm else None
    analyzer = MetaAnalyzer(cache=cache, gemini_client=gemini)
    report_gen = MarkdownReportGenerator()

    # Run analysis with progress
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Starting analysis...", total=None)

        def progress_callback(step: int, total: int, message: str):
            progress.update(task, description=f"[{step}/{total}] {message}")

        try:
            snapshot = analyzer.analyze(
                expansion=expansion,
                format=format,
                include_llm=include_llm,
                progress_callback=progress_callback,
            )
        except Exception as e:
            console.print(f"\n[red]Error during analysis:[/red] {e}")
            raise typer.Exit(1)

    # Display summary
    console.print("\n[bold]Analysis Complete![/bold]\n")

    # Color rankings table
    table = Table(title="Color Rankings")
    table.add_column("Rank", style="cyan")
    table.add_column("Color", style="green")
    table.add_column("Strength", justify="right")
    table.add_column("Playables", justify="right")

    for cs in snapshot.top_colors:
        table.add_row(
            str(cs.rank),
            cs.color,
            f"{cs.strength_score:.1f}",
            str(cs.playable_count),
        )

    console.print(table)
    console.print()

    # Top archetypes table
    if snapshot.archetypes:
        arch_table = Table(title="Top Archetypes")
        arch_table.add_column("Rank", style="cyan")
        arch_table.add_column("Archetype", style="green")
        arch_table.add_column("Win Rate", justify="right")

        for arch in snapshot.top_archetypes[:5]:
            arch_table.add_row(
                str(arch.rank),
                f"{arch.guild_name} ({arch.colors})",
                f"{arch.win_rate*100:.2f}%",
            )

        console.print(arch_table)
        console.print()

    # Sleepers and traps
    if snapshot.sleeper_cards:
        console.print("[bold yellow]Top Sleeper Cards:[/bold yellow]")
        for card in snapshot.sleeper_cards[:5]:
            console.print(f"  • {card.name} ({card.grade}) - Z: +{card.irregularity_z:.2f}")
        console.print()

    if snapshot.trap_cards:
        console.print("[bold red]Top Trap Cards:[/bold red]")
        for card in snapshot.trap_cards[:5]:
            console.print(f"  • {card.name} ({card.grade}) - Z: {card.irregularity_z:.2f}")
        console.print()

    # Generate reports
    console.print("[bold]Generating reports...[/bold]")

    md_path = report_gen.save_report(snapshot, output_dir, include_llm)
    console.print(f"  📄 Markdown: [cyan]{md_path}[/cyan]")

    json_path = export_json(snapshot, output_dir)
    console.print(f"  📊 JSON: [cyan]{json_path}[/cyan]")

    # Generate HTML report if requested
    if generate_html:
        html_gen = HtmlReportGenerator()
        html_path = html_gen.save_report(snapshot, output_dir, include_llm)
        console.print(f"  🌐 HTML Guide: [cyan]{html_path}[/cyan]")

    console.print("\n[bold green]Done![/bold green]")


@app.command()
def card(
    expansion: str = typer.Argument(..., help="Set code"),
    name: str = typer.Argument(..., help="Card name"),
    format: str = typer.Option(
        "PremierDraft",
        "--format", "-f",
        help="Draft format",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """
    Get detailed analysis for a specific card.

    Example:
        draft-analyzer card FDN "Lightning Strike"
    """
    setup_logging(verbose)

    console.print(f"\n[bold blue]Card Analysis: {name}[/bold blue]")
    console.print(f"Set: [green]{expansion}[/green] {format}\n")

    # Run quick analysis
    cache = CacheManager()
    analyzer = MetaAnalyzer(cache=cache)

    with console.status("Loading data..."):
        snapshot = analyzer.quick_analyze(expansion, format)

    # Find card
    card_lower = name.lower()
    card = next(
        (c for c in snapshot.all_cards if c.name.lower() == card_lower),
        None
    )

    if not card:
        # Try partial match
        matches = [c for c in snapshot.all_cards if card_lower in c.name.lower()]
        if matches:
            console.print(f"[yellow]Card not found. Did you mean:[/yellow]")
            for m in matches[:5]:
                console.print(f"  • {m.name}")
        else:
            console.print(f"[red]Card not found: {name}[/red]")
        raise typer.Exit(1)

    # Display card info
    console.print(f"[bold]{card.name}[/bold]")
    console.print(f"Colors: {card.colors} | Rarity: {card.rarity.value.title()}")
    console.print()

    info_table = Table(show_header=False, box=None)
    info_table.add_column("Metric", style="dim")
    info_table.add_column("Value")

    info_table.add_row("Grade", f"[bold]{card.grade}[/bold]")
    info_table.add_row("Composite Score", f"{card.composite_score:.1f}")
    info_table.add_row("GIH Win Rate", f"{card.stats.gih_wr*100:.2f}%")
    info_table.add_row("Adjusted WR", f"{card.adjusted_gih_wr*100:.2f}%")
    info_table.add_row("Games Analyzed", f"{card.stats.gih_games:,}")
    info_table.add_row("ALSA", f"{card.stats.alsa:.1f}")
    info_table.add_row("IWD", f"{card.stats.iwd*100:.2f}%")
    info_table.add_row("Stability", f"{card.stability_score:.1f}%")
    info_table.add_row("Classification", card.irregularity_type.title())

    console.print(info_table)

    # Archetype breakdown
    if card.stats.archetype_wrs:
        console.print("\n[bold]Archetype Performance:[/bold]")
        for colors, wr in sorted(
            card.stats.archetype_wrs.items(),
            key=lambda x: x[1],
            reverse=True
        ):
            games = card.stats.archetype_games.get(colors, 0)
            bar_len = int((wr - 0.4) * 100)  # Visual bar
            bar = "█" * max(0, bar_len)
            console.print(f"  {colors}: {wr*100:.1f}% {bar} ({games:,} games)")


@app.command()
def cache_stats():
    """Show cache statistics."""
    cache = CacheManager()
    stats = cache.get_stats()

    console.print("\n[bold]Cache Statistics[/bold]\n")
    console.print(f"Location: {stats['cache_dir']}")
    console.print(f"Total entries: {stats['total_entries']}")
    console.print(f"Valid entries: {stats['valid_entries']}")
    console.print(f"Expired entries: {stats['expired_entries']}")
    console.print(f"Total size: {stats['total_size_mb']:.2f} MB")


@app.command()
def cache_clear():
    """Clear all cached data."""
    cache = CacheManager()
    count = cache.clear_all()
    console.print(f"Cleared {count} cache entries.")


@app.command()
def version():
    """Show version information."""
    from src import __version__
    console.print(f"MTG Draft Analyzer v{__version__}")


if __name__ == "__main__":
    app()
