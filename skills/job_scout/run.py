"""
Job Scout skill — script OpenClaw (or main.py) calls.
Runs the job-scout pipeline: fetch job/industry sources → filter → send to Telegram.
"""
import os
import sys
import json
import hashlib

# Run from repo root so core and pipelines are importable
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.telegram import send_telegram, get_telegram_config, html_escape
from core.scraper import fetch_rss
from core.processor import is_relevant, summarize_batch


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


def main() -> None:
    os.chdir(_REPO_ROOT)

    config = load_json("config.json")
    bot_token = config.get("telegram_bot_token") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        bot_token, _ = get_telegram_config(config)

    # Prefer pipeline job_scout.json or jobs.json
    for name in ("job_scout", "jobs"):
        path = os.path.join("pipelines", f"{name}.json")
        if os.path.isfile(path):
            pipeline = load_json(path)
            break
    else:
        pipeline = {
            "title": "BirdEyeView | Job Scout",
            "chat_id": config.get("telegram_chat_id"),
            "sources": [],
            "keywords": ["job", "career", "hiring", "role", "position"],
            "max_items": 5,
            "use_ai_summary": False,
        }

    chat_id = pipeline.get("chat_id") or config.get("telegram_chat_id") or os.getenv("TELEGRAM_CHAT_ID")
    if not chat_id:
        raise ValueError("Set chat_id in pipeline or config (telegram_chat_id / TELEGRAM_CHAT_ID).")
    title = pipeline.get("title", "BirdEyeView | Job Scout")
    sources = pipeline.get("sources", [])
    keywords = pipeline.get("keywords", [])
    max_items = int(pipeline.get("max_items", 5))
    use_ai_summary = pipeline.get("use_ai_summary", False)
    model = config.get("model", "gpt-4o-mini")

    state_path = os.path.join("state", "seen_job_scout.json")
    seen = set(load_json(state_path)) if os.path.exists(state_path) else set()

    all_items = fetch_rss(sources) if sources else []
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

    from datetime import datetime
    today = datetime.now().strftime("%Y-%m-%d")
    if not top:
        send_telegram(bot_token, chat_id, f"No new relevant items for <b>{html_escape(title)}</b> ({today}).")
    else:
        lines = [f"<b>{html_escape(title)} ({today})</b>\n"]
        for i, it in enumerate(top, 1):
            headline = it.get("summary_line") or it.get("title", "")
            lines.append(f"{i}. <b>{html_escape(headline)}</b>\n{html_escape(it.get('link', ''))}\n")
        send_telegram(bot_token, chat_id, "\n".join(lines))

    save_json(state_path, list(seen))
    print(f"Job scout: fetched={len(all_items)} relevant={len(relevant)} sent={len(top)}")


if __name__ == "__main__":
    main()
