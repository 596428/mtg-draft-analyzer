# MTG Draft Meta Analyzer

> **[Live Demo: ECL Draft Guide](https://mtg-ecl-draft-guide.netlify.app)** | **[Metrics Guide](./METRICS_GUIDE.md)**

A comprehensive MTG Arena draft analysis system powered by 17lands data.

## Features

- **Card Scoring**: Wilson Score + Z-Score based composite card ratings
- **Color Analysis**: Single color strength and archetype analysis
- **Archetype Ranking**: Win rates and synergy analysis for all 2-color pairs
- **Format Speed Analysis**: Game length and play/draw statistics from 17lands API
- **Trophy Deck Analysis**: Insights from 7-x winning deck compositions
- **Sleeper/Trap Detection**: Automatically identifies undervalued and overvalued cards
- **Multi-Page HTML Guide**: Interactive web guide with filtering, search, and card modals
- **LLM Integration**: Strategic insights via Gemini API
- **Report Generation**: Markdown and JSON exports

## Live Demo

**Interactive Draft Guide**: https://mtg-ecl-draft-guide.netlify.app

The guide includes:
- **Overview**: Format speed analysis, key statistics, AI-generated strategy insights
- **Archetypes**: Tier rankings, detailed archetype breakdowns with key cards
- **Card Database**: Filterable card list by grade, rarity, and color
- **Special Cards**: Sleeper and trap card identification

## Installation

```bash
# Clone the repository
git clone https://github.com/596428/mtg-draft-analyzer.git
cd mtg-draft-analyzer

# Install with uv
uv sync
```

## Usage

### Analyze a Draft Format

```bash
# Basic analysis with HTML guide (no LLM)
uv run draft-analyzer analyze FDN --html --no-llm

# Full analysis with LLM interpretation (requires GEMINI_API_KEY)
uv run draft-analyzer analyze FDN --html

# Different format
uv run draft-analyzer analyze DSK --format QuickDraft --html
```

### Get Card Details

```bash
uv run draft-analyzer card FDN "Dreadwing Scavenger"
```

### Cache Management

```bash
# Show cache stats
uv run draft-analyzer cache-stats

# Clear cache
uv run draft-analyzer cache-clear
```

## Output Structure

Reports are saved to the `output/` directory:

```
output/{SET}_{FORMAT}_{DATE}/
├── index.html          # Overview page (main entry)
├── archetypes.html     # Archetype tier list and details
├── cards.html          # Card database with filters
├── special.html        # Sleeper and trap cards
├── css/
│   └── guide.css       # Shared styles
└── js/
    └── guide.js        # Shared JavaScript
```

Additional exports:
- `{SET}_{FORMAT}_{DATE}_meta_report.md` - Markdown report
- `{SET}_{FORMAT}_{DATE}_meta.json` - JSON data export

## Configuration

Edit `config/scoring.yaml` to customize:
- Scoring weights
- Calibration percentiles
- LLM settings
- Cache settings

## Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
GEMINI_API_KEY=your_api_key_here  # For LLM analysis
```

## Scoring System

### Composite Score (0-100)

Weighted combination of Z-normalized metrics:

| Metric | Weight | Description |
|--------|--------|-------------|
| **GIH WR** | 45% | Games In Hand Win Rate (Bayesian adjusted) |
| **IWD** | 20% | Improvement When Drawn |
| **ALSA** | 15% | Average Last Seen At (lower = better) |
| **OH WR** | 10% | Opening Hand Win Rate |
| **GD WR** | 10% | Games Drawn Win Rate |

### Bayesian Adjustment

- Wilson Score Lower Bound applied
- Cards with small sample sizes regress toward 50%
- High-sample cards reflect true performance more accurately

### Grades (13-tier system)

| Grade | Score Range | Description |
|-------|-------------|-------------|
| A+ | 90+ | Top-tier bomb |
| A | 80-89 | Bomb |
| A- | 75-79 | Near-bomb |
| B+ | 70-74 | Premium pick |
| B | 60-69 | Good pick |
| B- | 55-59 | Solid pick |
| C+ | 50-54 | Playable |
| C | 40-49 | Filler |
| C- | 35-39 | Weak filler |
| D+ | 32-34 | Below average |
| D | 28-31 | Sideboard |
| D- | 25-27 | Barely playable |
| F | 0-24 | Unplayable |

### Irregularity Detection

- **Sleeper**: Cards with high win rates relative to their pick position (undervalued)
- **Trap**: Cards with low win rates relative to their pick position (overvalued)

## Color Strength Calculation

| Component | Weight | Description |
|-----------|--------|-------------|
| Deck WR Strength | 35% | Average deck win rate for cards in this color |
| Archetype Success | 25% | Average win rate of related 2-color archetypes |
| Top Common Avg | 15% | Average score of top 10 commons |
| Top Uncommon Avg | 10% | Average score of top 5 uncommons |
| Bomb Factor | 10% | Quality of rare/mythic bombs |
| Depth Factor | 5% | Total count of playable cards |

## Project Structure

```
mtg-draft-analyzer/
├── config/
│   ├── scoring.yaml              # Scoring configuration
│   └── set_mechanics.yaml        # Set-specific mechanics for LLM
├── src/
│   ├── models/                   # Data models (Card, Archetype, Meta)
│   ├── data/                     # API clients (17lands, Scryfall)
│   ├── scoring/                  # Scoring algorithms
│   │   ├── card_scorer.py        # Wilson Score + Z-Score
│   │   ├── color_scorer.py       # Color/Archetype strength
│   │   ├── irregularity.py       # Sleeper/Trap detection
│   │   └── calibration.py        # Threshold calibration
│   ├── analysis/                 # Analysis orchestration
│   │   ├── color_meta.py         # Main analysis pipeline
│   │   └── trophy_analyzer.py    # Trophy deck analysis
│   ├── report/                   # Report generation
│   │   ├── html_gen.py           # Multi-page HTML guide
│   │   ├── markdown_gen.py       # Markdown report
│   │   └── json_export.py        # JSON export
│   ├── llm/                      # LLM integration (Gemini)
│   └── cli.py                    # CLI entry point
├── templates/
│   ├── guide_base.html.j2        # Base template with navigation
│   ├── guide_overview.html.j2    # Overview page
│   ├── guide_archetypes.html.j2  # Archetypes page
│   ├── guide_cards.html.j2       # Card database page
│   ├── guide_special.html.j2     # Special cards page
│   └── static/
│       ├── guide.css             # Shared CSS
│       └── guide.js              # Shared JavaScript
├── tests/                        # Test suite
└── output/                       # Generated reports (gitignored)
```

## API Data Sources

- **17lands**: Card ratings, color ratings, archetype data, play/draw statistics, trophy decks
- **Scryfall**: Card images and metadata
- **Gemini**: Strategic analysis and interpretation (optional)

## Screenshots

### Multi-Page HTML Guide

- **Overview**: Format speed analysis, stat cards, AI strategic insights
- **Archetypes**: Tier list with win rates, detailed tabs for each archetype
- **Card Database**: Filter by grade, rarity, color; search functionality; click-to-view modal
- **Special Cards**: Sleeper and trap cards with deviation scores

### Mobile Responsive

- Centered card modals (not bottom sheet)
- Horizontal scrolling navigation
- Touch-friendly filter buttons

## License

MIT
