# BirdsAiView

Fetch Malaysia news for OpenClaw to process. RSS/NewsAPI/Playwright → keyword filter → deduplicate → output JSON.

**OpenClaw** handles summarization and Telegram delivery.

## Directory layout

```
BirdsAiView/
├── config.json           # Optional (sources in pipelines)
├── main.py               # Fetch-only: outputs JSON to stdout
├── core/
│   ├── scraper.py        # RSS, NewsAPI, Playwright fetching
│   └── deduplicator.py   # Semantic title-similarity dedup
├── pipelines/            # JSON configs per topic (sources, keywords)
├── state/                # Persistence (seen item IDs)
└── skills/
    └── job_scout/        # Fetch job sources, output JSON
```

## Usage

```bash
# Fetch all pipelines, output JSON for OpenClaw
python main.py --fetch-only

# Fetch single pipeline
python main.py --fetch-only --pipeline property
```

Output format:
```json
{"items": [{"title": "...", "link": "...", "summary": "...", "source": "...", "pipeline": "property"}, ...]}
```

## Job Scout skill

```bash
python skills/job_scout/run.py
```

Outputs JSON to stdout. Add `pipelines/job_scout.json` or `pipelines/jobs.json` with `sources` and `keywords`.

## OpenClaw integration

1. OpenClaw invokes: `python /path/to/BirdsAiView/main.py --fetch-only`
2. Parse JSON from stdout
3. OpenClaw summarizes and sends to Telegram
