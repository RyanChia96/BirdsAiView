"""
BirdsAiView — Gateway to run pipelines and OpenClaw skills.
Morning digest: scrape → process → send relevant news to Telegram.

Usage:
  python main.py --digest              # Run all pipelines, one message
  python main.py --pipeline property  # Run single pipeline
  python main.py --test property      # Test Telegram
  python main.py --dry-run            # Skip Telegram send (with --pipeline or --digest)
  python main.py --cron               # Cron mode (quiet, no interactive output)
"""
import argparse
import json
import os
import sys
import hashlib
from datetime import datetime

from core.telegram import send_telegram, get_telegram_config, html_escape
from core.scraper import fetch_sources
from core.processor import (
    is_relevant,
    summarize_batch,
    summarize_digest_brief,
    compute_quality_score,
    classify_events_batch,
    score_impact_batch,
    sort_by_impact,
    select_with_source_diversity,
)
from core.deduplicator import deduplicate_semantic
from core.enricher import enrich_batch


# --------- helpers ----------
def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def item_id(title: str, link: str) -> str:
    raw = f"{_norm(title)}|{_norm(link)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def format_message(title: str, items: list[dict], include_source: bool = True) -> str:
    """Format Telegram message. include_source adds source per story (InsightsPanel style)."""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"<b>{html_escape(title)} ({today})</b>\n"]
    for i, it in enumerate(items, 1):
        headline = it.get("summary_line") or it.get("title", "")
        line = f"{i}. <b>{html_escape(headline)}</b>"
        if include_source and it.get("source"):
            src = it.get("source", "")
            if isinstance(src, str) and "/" in src:
                src = src.split("/")[2] if len(src.split("/")) > 2 else src
            line += f"\n   <i>{html_escape(src)}</i>"
        line += f"\n{html_escape(it.get('link', ''))}\n"
        lines.append(line)
    return "\n".join(lines)


DIGEST_PIPELINES = ("property", "inflation", "ma", "dev_projects", "tech")
SECTION_LABELS = {
    "inflation": "📈 Inflation & Economy",
    "ma": "🏢 M&A & Corporate",
    "dev_project": "🏗 Development Projects",
    "tech_announcement": "💻 Tech & Software",
    "property": "🏠 Property",
    "job": "💼 Jobs",
}


def _run_pipeline_items(pipeline_name: str, config: dict) -> tuple[list[dict], set, list[dict]]:
    """Run pipeline logic and return (top_items, seen_ids, all_fresh). Used by run_pipeline and run_digest."""
    pipeline_path = os.path.join("pipelines", f"{pipeline_name}.json")
    if not os.path.isfile(pipeline_path):
        return [], set(), []
    pipeline = load_json(pipeline_path)
    sources = pipeline.get("sources", [])
    keywords = pipeline.get("keywords", [])
    event_types = pipeline.get("event_types", [])
    max_items = int(pipeline.get("max_items", 5))
    use_ai_summary = pipeline.get("use_ai_summary", False)
    model = config.get("model", "gpt-4o-mini")

    state_path = os.path.join("state", f"seen_{pipeline_name}.json")
    seen = set(load_json(state_path)) if os.path.exists(state_path) else set()

    all_items = fetch_sources(sources)
    relevant = [it for it in all_items if is_relevant(it, keywords)]

    fresh = []
    for it in relevant:
        iid = item_id(it.get("title", ""), it.get("link", ""))
        if iid not in seen:
            fresh.append(it)
            seen.add(iid)

    for it in fresh:
        compute_quality_score(it)
    fresh = deduplicate_semantic(fresh)
    classify_events_batch(fresh, model=model)
    if event_types:
        fresh = [it for it in fresh if it.get("event_type") in event_types]
    score_impact_batch(fresh, model=model)
    enrich_batch(fresh)
    fresh = sort_by_impact(fresh)

    top = select_with_source_diversity(fresh, max_count=max_items)
    if use_ai_summary and top:
        summarize_batch(top, model=model)

    return top, seen, fresh


def run_pipeline(pipeline_name: str, test_only: bool = False, dry_run: bool = False, cron: bool = False) -> None:
    """Run a single pipeline: load config → fetch → filter → dedupe → send."""
    config = load_json("config.json")
    bot_token = config.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        bot_token, _ = get_telegram_config(config)

    pipeline_path = os.path.join("pipelines", f"{pipeline_name}.json")
    pipeline = load_json(pipeline_path)
    chat_id = pipeline.get("chat_id") or config.get("telegram_chat_id")
    if not chat_id:
        raise ValueError(f"Set chat_id in pipeline {pipeline_name} or config.json")
    title = pipeline.get("title", f"BirdEyeView | {pipeline_name}")

    if test_only:
        if not dry_run:
            send_telegram(bot_token, chat_id, f"✅ Test OK: posting to <b>{html_escape(title)}</b>")
        if not cron:
            print("Sent test message.")
        return

    top, seen, _ = _run_pipeline_items(pipeline_name, config)
    state_path = os.path.join("state", f"seen_{pipeline_name}.json")
    save_json(state_path, list(seen))

    if not dry_run:
        if not top:
            send_telegram(bot_token, chat_id, f"No new relevant items for <b>{html_escape(title)}</b> today.")
        else:
            send_telegram(bot_token, chat_id, format_message(title, top))

    if not cron:
        print(f"Pipeline {pipeline_name}: sent {len(top)} items" + (" [dry-run, Telegram skipped]" if dry_run else ""))


def format_digest_message(items_by_section: dict[str, list[dict]], brief: str | None = None) -> str:
    """Format consolidated digest with sections. Optional brief (2-3 sentence AI summary) at top."""
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"<b>🇲🇾 BirdEyeView Daily Digest ({today})</b>\n"]
    if brief and brief.strip():
        lines.append(html_escape(brief.strip()))
        lines.append("")
    for section_key in ("inflation", "ma", "dev_project", "tech_announcement", "property", "job"):
        items = items_by_section.get(section_key, [])
        if not items:
            continue
        label = SECTION_LABELS.get(section_key, section_key)
        lines.append(f"\n<b>{html_escape(label)}</b>")
        for i, it in enumerate(items, 1):
            headline = it.get("summary_line") or it.get("title", "")
            lines.append(f"{i}. <b>{html_escape(headline)}</b>\n{html_escape(it.get('link', ''))}")
    return "\n".join(lines) if len(lines) > 1 else ""


def run_digest(dry_run: bool = False, cron: bool = False) -> None:
    """Run all pipelines, merge by impact, dedupe globally, send one consolidated message."""
    config = load_json("config.json")
    bot_token = config.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        bot_token, _ = get_telegram_config(config)
    chat_id = config.get("digest_chat_id") or config.get("telegram_chat_id")
    if not chat_id:
        p0 = os.path.join("pipelines", f"{DIGEST_PIPELINES[0]}.json")
        if os.path.isfile(p0):
            chat_id = load_json(p0).get("chat_id")
    if not chat_id:
        raise ValueError("Set digest_chat_id or telegram_chat_id in config.json for digest")

    all_items: list[dict] = []
    for name in DIGEST_PIPELINES:
        top, seen, _ = _run_pipeline_items(name, config)
        state_path = os.path.join("state", f"seen_{name}.json")
        save_json(state_path, list(seen))
        for it in top:
            it["_section"] = it.get("event_type", "other")
            all_items.append(it)

    seen_ids: set[str] = set()
    unique: list[dict] = []
    for it in all_items:
        iid = item_id(it.get("title", ""), it.get("link", ""))
        if iid not in seen_ids:
            seen_ids.add(iid)
            unique.append(it)

    unique = sort_by_impact(unique)
    items_by_section: dict[str, list[dict]] = {}
    for it in unique:
        sec = it.get("_section", "other")
        if sec not in items_by_section:
            items_by_section[sec] = []
        items_by_section[sec].append(it)

    brief = None
    if config.get("digest_use_brief") and unique:
        brief = summarize_digest_brief(unique[:8], model=config.get("model", "gpt-4o-mini"))
    msg = format_digest_message(items_by_section, brief=brief)
    if not dry_run:
        if not msg:
            send_telegram(bot_token, chat_id, "No new relevant items in digest today.")
        else:
            send_telegram(bot_token, chat_id, msg)
    if not cron:
        print(f"Digest: {len(unique)} unique items sent" + (" [dry-run, Telegram skipped]" if dry_run else ""))


def run_skill(skill_name: str) -> None:
    """Run an OpenClaw-style skill (e.g. job_scout). Skills live in skills/<name>/run.py."""
    run_path = os.path.join("skills", skill_name, "run.py")
    if not os.path.isfile(run_path):
        print(f"Skill not found: {run_path}")
        sys.exit(1)
    # Run skill in same process so it can use core and config
    import importlib.util
    spec = importlib.util.spec_from_file_location(f"skills.{skill_name}.run", run_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if hasattr(mod, "main"):
        mod.main()
    else:
        print(f"No main() in {run_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="BirdsAiView — Daily surveillance digest")
    parser.add_argument("--digest", action="store_true", help="Run all pipelines, one consolidated message")
    parser.add_argument("--pipeline", metavar="NAME", help="Run single pipeline")
    parser.add_argument("--test", metavar="NAME", help="Test Telegram for pipeline")
    parser.add_argument("--skill", metavar="NAME", help="Run OpenClaw skill")
    parser.add_argument("--dry-run", action="store_true", help="Skip Telegram send")
    parser.add_argument("--cron", action="store_true", help="Cron mode (quiet output)")
    args = parser.parse_args()

    dry_run = args.dry_run
    cron = args.cron

    if args.digest:
        run_digest(dry_run=dry_run, cron=cron)
        return
    if args.pipeline:
        run_pipeline(args.pipeline, test_only=False, dry_run=dry_run, cron=cron)
        return
    if args.test:
        run_pipeline(args.test, test_only=True, dry_run=dry_run, cron=cron)
        return
    if args.skill:
        run_skill(args.skill)
        return

    print("BirdsAiView — Gateway for pipelines and skills")
    print("  python main.py --digest [--dry-run] [--cron]")
    print("  python main.py --pipeline <name> [--dry-run] [--cron]")
    print("  python main.py --test <name>")
    print("  python main.py --skill <name>")
    sys.exit(1)


if __name__ == "__main__":
    main()
