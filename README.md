# BirdsAiView

Morning digest: scrape news and job postings → filter and summarize → send to your Telegram channel. Structured for **OpenClaw** integration and future hosting.

## Directory layout

```
BirdsAiView/
├── .env.example          # Template for API keys (copy to .env)
├── config.json           # Global settings (create from config.example.json)
├── main.py               # Gateway: run pipelines or skills
├── core/                 # Shared logic
│   ├── telegram.py       # Send messages to Telegram
│   ├── scraper.py        # RSS (+ Playwright stub) fetching
│   └── processor.py      # AI summarization & relevance
├── pipelines/            # JSON configs per topic
│   ├── property.json
│   └── industries.json
├── state/                # Persistence (seen items, no duplicates)
│   └── seen_<pipeline>.json
└── skills/               # OpenClaw-style skills
    └── job_scout/
        ├── SKILL.md      # Instructions for the AI
        └── run.py        # Script to run this skill
```

## How it works

1. **Pipelines** — Each pipeline is a JSON file: RSS `sources`, `keywords`, `chat_id`, and options like `max_items` and `use_ai_summary`. The gateway loads a pipeline, fetches feeds, filters by keywords, dedupes using `state/`, and sends one Telegram message.

2. **Core** — `scraper` pulls from RSS (and later Playwright for job boards). `processor` does keyword relevance and optional OpenAI summarization. `telegram` sends the digest.

3. **Skills** — OpenClaw-style modules under `skills/<name>/`. Each has a `SKILL.md` (instructions for the AI) and `run.py` (entrypoint). They use the same core and can target a pipeline (e.g. `pipelines/job_scout.json`) or built-in defaults. Run via `python main.py --skill job_scout`.

4. **State** — `state/seen_<pipeline>.json` stores item IDs so you don’t get the same link twice across runs (e.g. daily).

## Quick start

1. Copy `.env.example` to `.env` and set `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`. Optionally `OPENAI_API_KEY` for summarization.
2. Copy `config.example.json` to `config.json` and set `telegram_bot_token`, `telegram_chat_id` (or rely on .env). Per-pipeline `chat_id` in each pipeline JSON overrides for that topic.
3. Run a pipeline:
   - `python main.py --test property` — send a test message.
   - `python main.py --pipeline property` — full run (fetch → filter → send).
4. Run a skill: `python main.py --skill job_scout` (add `pipelines/job_scout.json` or `pipelines/jobs.json` with `sources` and `chat_id` for real data).

## Morning automation

Schedule `main.py` (e.g. cron or Task Scheduler) to run every morning:

- `python main.py --pipeline property`
- `python main.py --skill job_scout`

Later you can point OpenClaw at the same `skills/` and workspace so the agent can run these skills; the layout is ready for migration to a separate host.
