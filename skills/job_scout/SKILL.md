# Job Scout Skill

Instructions for the AI / OpenClaw when running this skill.

## Purpose
- Scout job postings and industry-related opportunities from configured sources.
- Filter by keywords and relevance so only useful items are forwarded.
- Summarize when needed so the morning digest is scannable.

## Behavior
- Use **RSS** (and optionally Playwright) via `core.scraper` to fetch job and industry news.
- Use **relevance** (keywords + optional AI) via `core.processor` to keep only matching items.
- Send the digest to Telegram using `core.telegram` and the pipeline’s `chat_id`.

## Pipeline
- Prefer pipeline config: `pipelines/job_scout.json` or `pipelines/jobs.json`.
- If missing, the skill can fall back to defaults (sources and keywords) defined in `run.py`.

## Output
- One Telegram message per run: title, optional one-line summary, and link for each new item.
- State is stored under `state/seen_job_scout.json` (or per-pipeline) to avoid duplicates.
