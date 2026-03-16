# Surveillance Enricher Skill

Instructions for the AI / OpenClaw when running this skill.

## Purpose
- Research and verify M&A and tech announcement news items.
- Extract confirmed entities, related companies, and timeline.
- Enable manual "deep dive" from Telegram: user forwards link → skill researches → returns report.

## Behavior
- Accepts item JSON via stdin or file path argument.
- Calls OpenClaw Web Researcher (or local LLM) to research the headline and summary.
- Returns enriched JSON with: confirmed_entities, related_companies, timeline, verification_notes.

## Usage
- From main.py: `python main.py --skill surveillance_enricher` (with item in stdin)
- From OpenClaw: Invoke skill with item payload for deep research on a specific news piece.

## Output
- Enriched item JSON with research findings attached.
- Or formatted text report for Telegram reply.
