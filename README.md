# EDS Researcher

Agentic AI research tool that automatically discovers, categorizes, and reports on pain management treatments for Ehlers-Danlos Syndrome (EDS). Targets symptoms like joint pain, neuropathy, muscle pain, and brain fog.

The agent runs weekly, learns from previous findings, and produces reports suitable for discussing treatment options with medical providers.

## How It Works

Each run executes a 4-stage pipeline:

1. **PLAN** — Queries the knowledge database for known treatments, gaps, and pending leads, then generates adaptive search queries via Grok
2. **SEARCH** — Executes queries across 5 data sources (PubMed, Reddit, X/Twitter, ClinicalTrials.gov, Google Scholar)
3. **ANALYZE** — Grok extracts treatments, scores evidence quality, identifies providers, and flags new leads
4. **LEARN** — Updates the database with findings and generates new search leads for the next run

## Evidence Tiers

All findings are kept permanently and labeled by evidence quality:

| Tier | Label | Description |
|------|-------|-------------|
| T1 | Peer-Reviewed | Published RCTs, meta-analyses, systematic reviews |
| T2 | Clinical/Emerging | Active/completed clinical trials, case studies |
| T3 | Professional Opinion | Doctor recommendations, conference presentations |
| T4 | Anecdotal — Multiple | Consistent reports from multiple community members |
| T5 | Anecdotal — Single | Individual report from one source |
| T6 | Theoretical/Lead | Mentioned but no direct evidence yet |

## Setup

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager

### Install

```bash
git clone https://github.com/txdadlab/eds-researcher.git
cd eds-researcher
uv sync
```

### API Keys

Copy `.env.example` to `.env` and fill in your keys:

```bash
cp .env.example .env
```

| Service | Variable | How to Get |
|---------|----------|------------|
| xAI (Grok) | `XAI_API_KEY` | [console.x.ai](https://console.x.ai) |
| PubMed | `NCBI_API_KEY` | [ncbi.nlm.nih.gov/account](https://www.ncbi.nlm.nih.gov/account/) |
| Reddit | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET` | [reddit.com/prefs/apps](https://www.reddit.com/prefs/apps) — create a "script" app |

### Initialize

```bash
uv run eds-researcher init
```

## Usage

### Run the full pipeline

```bash
uv run eds-researcher run
```

### Generate reports only

```bash
uv run eds-researcher report full       # Full treatment compendium
uv run eds-researcher report delta -d 7 # Changes in the last 7 days
```

### Schedule weekly runs (macOS)

```bash
uv run eds-researcher schedule --weekday 1 --hour 9  # Monday at 9 AM
```

## Reports

Two report types are generated as Markdown files in `data/reports/`:

- **Full Compendium** — Complete treatment database organized by symptom, with evidence summaries, side effects, costs, providers, and source links
- **Weekly Delta** — Only new findings since last report — new treatments, evidence updates, new providers, and search effectiveness stats

## Configuration

Edit `config.yaml` to customize symptoms, search parameters, data sources, and Grok model selection. See the comments in the file for details.

## Running Tests

```bash
uv run pytest tests/ -v
```

## Disclaimer

This tool is for informational purposes and discussion with medical providers. It is not medical advice.
