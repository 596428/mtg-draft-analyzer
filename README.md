# MTG Draft Meta Analyzer

> **[📊 ECL Draft Guide (Live)](https://mtg-ecl-draft-guide.netlify.app/ecl_premierdraft_2026-01-24_draft_guide)** | **[📖 Metrics Guide](./METRICS_GUIDE.md)**

17lands 데이터를 활용한 MTG Arena 드래프트 메타 분석 시스템

## Live Demo

**Interactive Draft Guide**: https://mtg-ecl-draft-guide.netlify.app

## Features

- **Card Scoring**: Wilson Score + Z-Score 기반 카드 종합 점수 산출
- **Color Analysis**: 색깔별 강도 및 아키타입 분석
- **Archetype Ranking**: 10개 2색 조합(길드)별 승률 및 시너지 분석
- **Sleeper/Trap Detection**: 저평가/고평가 카드 자동 탐지
- **Interactive HTML Guide**: 필터링, 검색, 모달 기능이 포함된 웹 가이드 생성
- **LLM Integration**: Gemini API를 통한 전략 해석
- **Markdown/JSON Reports**: 분석 결과 보고서 자동 생성

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
# Basic analysis with HTML guide
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

## Output

Reports are saved to the `output/` directory:
- `{SET}_{FORMAT}_{DATE}_draft_guide.html` - Interactive HTML guide
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

- Wilson Score Lower Bound 적용
- 샘플 수가 적은 카드는 50%로 회귀
- 대량 샘플 카드의 실제 성능이 더 정확히 반영됨

### Grades

| Grade | Score Range | Description |
|-------|-------------|-------------|
| A+ | 90+ | 최상위 폭탄 |
| A | 80-89 | 폭탄급 |
| A- | 75-79 | 준폭탄 |
| B+ | 70-74 | 우선 픽 |
| B | 60-69 | 좋은 픽 |
| B- | 55-59 | 준수한 픽 |
| C+ | 50-54 | 플레이어블 |
| C | 40-49 | 필러급 |
| C- | 35-39 | 약한 필러 |
| D | 30-34 | 사이드보드 |
| F | 0-29 | 플레이 불가 |

### Irregularity Detection

- **Sleeper**: 픽 순위 대비 높은 승률을 보이는 저평가 카드
- **Trap**: 픽 순위 대비 낮은 승률을 보이는 고평가 카드

## Color Strength Calculation

| Component | Weight | Description |
|-----------|--------|-------------|
| Deck WR Strength | 35% | 해당 색 카드의 덱 승률 평균 |
| Archetype Success | 25% | 관련 2색 조합들의 평균 승률 |
| Top Common Avg | 15% | 상위 커먼 10장의 평균 점수 |
| Top Uncommon Avg | 10% | 상위 언커먼 5장의 평균 점수 |
| Bomb Factor | 10% | 레어/미식 폭탄의 품질 |
| Depth Factor | 5% | 플레이어블 카드의 총 개수 |

## Project Structure

```
mtg-draft-analyzer/
├── config/
│   └── scoring.yaml          # Configuration
├── src/
│   ├── models/               # Data models (Card, Archetype, Meta)
│   ├── data/                 # API clients (17lands, Scryfall)
│   ├── scoring/              # Scoring algorithms
│   │   ├── card_scorer.py    # Wilson Score + Z-Score
│   │   ├── color_scorer.py   # Color/Archetype strength
│   │   ├── irregularity.py   # Sleeper/Trap detection
│   │   └── calibration.py    # Threshold calibration
│   ├── analysis/             # Analysis orchestration
│   ├── report/               # Report generation
│   │   ├── html_gen.py       # Interactive HTML guide
│   │   ├── markdown_gen.py   # Markdown report
│   │   └── json_export.py    # JSON export
│   ├── llm/                  # LLM integration (Gemini)
│   └── cli.py                # CLI entry point
├── templates/
│   └── draft_guide.html.j2   # HTML template
├── tests/                    # Test suite
└── output/                   # Generated reports (gitignored)
```

## API Data Sources

- **17lands**: Card ratings, color ratings, archetype data
- **Scryfall**: Card images and metadata
- **Gemini**: Strategic analysis and interpretation (optional)

## Screenshots

### Interactive HTML Guide
- Card filtering by grade, rarity, color
- Search functionality
- Click-to-view card modal with detailed stats
- Archetype tabs with key cards
- Sleeper & Trap card highlighting

## License

MIT
