"""
BirdsAiView — Gateway to run pipelines and OpenClaw skills.
Morning digest: scrape → process → send relevant news to Telegram.
"""
import json
import os
import sys
import hashlib
from datetime import datetime

from core.telegram import send_telegram, get_telegram_config, html_escape
from core.scraper import fetch_rss
from core.processor import is_relevant, summarize_batch


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


def format_message(title: str, items: list[dict]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"<b>{html_escape(title)} ({today})</b>\n"]
    for i, it in enumerate(items, 1):
        headline = it.get("summary_line") or it.get("title", "")
        lines.append(f"{i}. <b>{html_escape(headline)}</b>\n{html_escape(it.get('link', ''))}\n")
    return "\n".join(lines)


def run_pipeline(pipeline_name: str, test_only: bool = False) -> None:
    """Run a single pipeline: load config → fetch → filter → dedupe → send."""
    config = load_json("config.json")
    bot_token = config.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        bot_token, _ = get_telegram_config(config)

    pipeline_path = os.path.join("pipelines", f"{pipeline_name}.json")
    pipeline = load_json(pipeline_path)

    chat_id = pipeline["chat_id"]
    title = pipeline.get("title", f"BirdEyeView | {pipeline_name}")
    sources = pipeline.get("sources", [])
    keywords = pipeline.get("keywords", [])
    max_items = int(pipeline.get("max_items", 5))
    use_ai_summary = pipeline.get("use_ai_summary", False)
    model = config.get("model", "gpt-4o-mini")

    if test_only:
        send_telegram(bot_token, chat_id, f"✅ Test OK: posting to <b>{html_escape(title)}</b>")
        print("Sent test message.")
        return

    state_path = os.path.join("state", f"seen_{pipeline_name}.json")
    seen = set(load_json(state_path)) if os.path.exists(state_path) else set()

    all_items = fetch_rss(sources)
    relevant = [it for it in all_items if is_relevant(it, keywords)]

    fresh = []
    for it in relevant:
        iid = item_id(it.get("title", ""), it.get("link", ""))
        if iid not in seen:
            fresh.append(it)
            seen.add(iid)

    top = fresh[:max_items]
    if use_ai_summary and top:
        summarize_batch(top, model=model)

    if not top:
        send_telegram(bot_token, chat_id, f"No new relevant items for <b>{html_escape(title)}</b> today.")
    else:
        send_telegram(bot_token, chat_id, format_message(title, top))

    save_json(state_path, list(seen))
    print(f"Fetched: {len(all_items)} | Relevant: {len(relevant)} | New sent: {len(top)}")


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
    if "--pipeline" in sys.argv:
        idx = sys.argv.index("--pipeline")
        name = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else None
        if not name:
            print("Usage: python main.py --pipeline <name>")
            sys.exit(1)
        run_pipeline(name, test_only=False)
    elif "--test" in sys.argv:
        idx = sys.argv.index("--test")
        name = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else None
        if not name:
            print("Usage: python main.py --test <pipeline_name>")
            sys.exit(1)
        run_pipeline(name, test_only=True)
    elif "--skill" in sys.argv:
        idx = sys.argv.index("--skill")
        name = sys.argv[idx + 1] if len(sys.argv) > idx + 1 else None
        if not name:
            print("Usage: python main.py --skill <skill_name>")
            sys.exit(1)
        run_skill(name)
    else:
        print("BirdsAiView — Gateway for pipelines and skills")
        print("  python main.py --pipeline property   # Run pipeline")
        print("  python main.py --test property        # Test Telegram for pipeline")
        print("  python main.py --skill job_scout     # Run OpenClaw skill")
        sys.exit(1)


if __name__ == "__main__":
    main()
