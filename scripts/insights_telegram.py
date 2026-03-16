#!/usr/bin/env python3
"""
Insights-to-Telegram pipeline — Python version of InsightsPanel.ts

Pipeline: fetch feeds → clean text → deduplicate → AI summarization → Telegram

Usage:
  python scripts/insights_telegram.py                    # run once
  python scripts/insights_telegram.py --dry-run          # skip Telegram
  python scripts/insights_telegram.py --cron             # cron-friendly (no interactive output)

Env vars:
  OPENAI_API_KEY or GROQ_API_KEY    — for AI summarization
  TELEGRAM_BOT_TOKEN                 — Bot token from @BotFather
  TELEGRAM_CHAT_ID                   — Chat/channel ID to send messages to
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from html import unescape

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import feedparser

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

# ─── Feed configuration (mirrors InsightsPanel / config/feeds.ts) ───

FEEDS: list[dict[str, str]] = [
    {"name": "Reuters World", "url": "https://www.reuters.com/rssfeed/worldNews"},
    {"name": "AP News", "url": "https://rsshub.app/apnews/topics/world"},
    {"name": "BBC World", "url": "https://feeds.bbci.co.uk/news/world/rss.xml"},
    {"name": "Guardian World", "url": "https://www.theguardian.com/world/rss"},
    {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml"},
    {"name": "CNN World", "url": "http://rss.cnn.com/rss/cnn_world.rss"},
    {"name": "EuroNews", "url": "https://www.euronews.com/rss?format=mrss"},
    {"name": "France 24", "url": "https://www.france24.com/en/rss"},
    {"name": "Foreign Policy", "url": "https://foreignpolicy.com/feed/"},
    {"name": "The Diplomat", "url": "https://thediplomat.com/feed/"},
    {"name": "Atlantic Council", "url": "https://www.atlanticcouncil.org/feed/"},
    {"name": "War on the Rocks", "url": "https://warontherocks.com/feed/"},
]

MILITARY_KEYWORDS = ["war", "armada", "invasion", "airstrike", "strike", "missile", "troops", "deployed", "offensive", "artillery", "bomb", "combat", "fleet", "warship"]
VIOLENCE_KEYWORDS = ["killed", "dead", "death", "shot", "blood", "massacre", "casualties", "wounded", "injured", "violent", "clashes", "gunfire", "shooting"]
UNREST_KEYWORDS = ["protest", "protests", "uprising", "revolt", "revolution", "riot", "demonstration", "unrest", "coup", "martial law", "curfew"]
FLASHPOINT_KEYWORDS = ["iran", "tehran", "russia", "moscow", "china", "beijing", "taiwan", "ukraine", "kyiv", "israel", "gaza", "syria", "yemen", "nato", "pentagon"]
CRISIS_KEYWORDS = ["crisis", "emergency", "catastrophe", "disaster", "collapse", "sanctions", "ultimatum", "threat", "escalation", "breaking", "urgent"]
DEMOTE_KEYWORDS = ["ceo", "earnings", "stock", "startup", "revenue", "quarterly", "ipo"]


def clean_text(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"ALERT\[\w+\]:\s*", "", s)
    s = re.sub(r"AREAS\[\w+\]:\s*", "", s)
    s = unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def normalize_title(title: str) -> str:
    t = clean_text(title).lower()
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"[^\w\s]", "", t)
    return t


def fetch_feeds() -> list[dict]:
    items: list[dict] = []
    headers = {"User-Agent": "BirdsAiView-Insights/1.0"}
    for feed_cfg in FEEDS:
        try:
            d = feedparser.parse(feed_cfg["url"], request_headers=headers)
            for entry in d.entries[:20]:
                title = getattr(entry, "title", "") or ""
                link = getattr(entry, "link", "") or ""
                pub = None
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    pub = datetime(*entry.published_parsed[:6])
                items.append({
                    "title": clean_text(title),
                    "link": link,
                    "source": feed_cfg["name"],
                    "published": pub,
                })
        except Exception as e:
            if "--cron" not in sys.argv:
                print(f"[WARN] {feed_cfg['name']}: {e}", file=sys.stderr)
    return items


def deduplicate(items: list[dict], by: str = "title") -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for item in items:
        key = normalize_title(item["title"]) if by == "title" else item.get("link", "")
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def score_item(item: dict) -> float:
    score = 0.0
    t = item.get("title", "").lower()

    v = sum(1 for k in VIOLENCE_KEYWORDS if k in t)
    if v:
        score += 100 + v * 25

    m = sum(1 for k in MILITARY_KEYWORDS if k in t)
    if m:
        score += 80 + m * 20

    u = sum(1 for k in UNREST_KEYWORDS if k in t)
    if u:
        score += 70 + u * 18

    f = sum(1 for k in FLASHPOINT_KEYWORDS if k in t)
    if f:
        score += 60 + f * 15

    if (v or u) and f:
        score *= 1.5

    c = sum(1 for k in CRISIS_KEYWORDS if k in t)
    if c:
        score += 30 + c * 10

    d = sum(1 for k in DEMOTE_KEYWORDS if k in t)
    if d:
        score *= 0.3

    if item.get("published"):
        age_h = (datetime.now() - item["published"]).total_seconds() / 3600
        recency = max(0.5, 1 - age_h / 12)
        score *= recency

    return score


def select_top(items: list[dict], max_count: int = 8) -> list[dict]:
    scored = [(item, score_item(item)) for item in items]
    scored.sort(key=lambda x: -x[1])
    selected: list[dict] = []
    source_count: dict[str, int] = {}
    max_per_source = 3
    for item, _ in scored:
        c = source_count.get(item["source"], 0)
        if c < max_per_source:
            selected.append(item)
            source_count[item["source"]] = c + 1
        if len(selected) >= max_count:
            break
    return selected


def summarize_with_ai(titles: list[str]) -> str:
    groq_key = os.environ.get("GROQ_API_KEY")
    openai_key = os.environ.get("OPENAI_API_KEY")
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
        groq_key = groq_key or cfg.get("groq_api_key")
        openai_key = openai_key or cfg.get("openai_api_key")
    except Exception:
        pass

    if not groq_key and not openai_key:
        return "⚠️ No API key (OPENAI_API_KEY or GROQ_API_KEY). Skipping AI summary."

    combined = ". ".join(t[:80] for t in titles[:5])
    prompt = f"Summarize the most important headlines in 2–3 concise sentences (under 80 words): {combined}"

    try:
        if groq_key:
            client = OpenAI(api_key=groq_key, base_url="https://api.groq.com/openai/v1")
            r = client.chat.completions.create(
                model=os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
            )
        else:
            client = OpenAI(api_key=openai_key)
            r = client.chat.completions.create(
                model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=150,
            )
        summary = (r.choices[0].message.content or "").strip()
        return summary if summary else "No summary generated."
    except Exception as e:
        return f"⚠️ AI summarization failed: {e}"


def send_telegram(text: str) -> bool:
    import urllib.request
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
        token = token or cfg.get("telegram_bot_token")
        chat_id = chat_id or cfg.get("telegram_chat_id")
    except Exception:
        pass
    if not token or not chat_id:
        return False
    try:
        body = json.dumps({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status in (200, 201)
    except Exception as e:
        if "--cron" not in sys.argv:
            print(f"[WARN] Telegram send failed: {e}", file=sys.stderr)
        return False


def escape_html(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def format_message(brief: str, stories: list[dict]) -> str:
    lines = [
        "<b>🌍 World Brief</b>",
        "",
        escape_html(brief),
        "",
        "<b>📌 Top stories</b>",
    ]
    for i, s in enumerate(stories[:5], 1):
        title = s["title"][:80] + ("..." if len(s["title"]) > 80 else "")
        lines.append(f"{i}. {escape_html(title)}")
        lines.append(f"   <i>{s['source']}</i>")
    lines.append("")
    lines.append(f"<i>Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M')} UTC</i>")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Insights pipeline → Telegram")
    parser.add_argument("--dry-run", action="store_true", help="Skip Telegram send")
    parser.add_argument("--cron", action="store_true", help="Cron mode (quiet, exit 0)")
    args = parser.parse_args()

    items = fetch_feeds()
    if not items:
        if not args.cron:
            print("[WARN] No items fetched.", file=sys.stderr)
        return 0

    items = deduplicate(items)
    if not items:
        if not args.cron:
            print("[WARN] No items after dedup.", file=sys.stderr)
        return 0

    top = select_top(items, max_count=8)
    titles = [s["title"] for s in top[:5]]
    brief = summarize_with_ai(titles)
    msg = format_message(brief, top)

    if not args.cron:
        print(msg)
        print()

    if not args.dry_run:
        ok = send_telegram(msg)
        if not args.cron:
            print(f"Telegram: {'sent' if ok else 'skipped or failed'}")
    else:
        if not args.cron:
            print("[DRY-RUN] Skipped Telegram send.")

    return 0


if __name__ == "__main__":
    if OpenAI is None:
        print("Install: pip install feedparser openai", file=sys.stderr)
        sys.exit(1)
    sys.exit(main())
