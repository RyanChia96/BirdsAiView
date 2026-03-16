"""
BirdsAiView — Fetch news for OpenClaw to process.
Fetches from RSS/NewsAPI/Playwright, filters by keywords, deduplicates. Outputs JSON.
OpenClaw handles summarization and Telegram delivery.

Usage:
  python main.py --fetch-only              # Output JSON to stdout (all pipelines)
  python main.py --fetch-only --pipeline property  # Single pipeline
"""
import argparse
import json
import os
import sys
import hashlib

from core.scraper import fetch_sources
from core.deduplicator import deduplicate_semantic


DIGEST_PIPELINES = ("property", "inflation", "ma", "dev_projects", "tech")


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def item_id(title: str, link: str) -> str:
    raw = f"{_norm(title)}|{_norm(link)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def is_relevant(item: dict, keywords: list[str]) -> bool:
    """Keyword-based relevance (no API)."""
    text = _norm(item.get("title", "") + " " + item.get("summary", ""))
    return any(_norm(kw) in text for kw in keywords if (kw or "").strip())


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_pipeline_items(pipeline_name: str) -> list[dict]:
    """Fetch, filter by keywords, dedupe. Returns list of items."""
    pipeline_path = os.path.join("pipelines", f"{pipeline_name}.json")
    if not os.path.isfile(pipeline_path):
        return []
    pipeline = load_json(pipeline_path)
    sources = pipeline.get("sources", [])
    keywords = pipeline.get("keywords", [])
    max_items = int(pipeline.get("max_items", 20))

    all_items = fetch_sources(sources)
    relevant = [it for it in all_items if is_relevant(it, keywords)]
    items = deduplicate_semantic(relevant)[:max_items]
    return items


def fetch_all() -> list[dict]:
    """Fetch from all pipelines, merge and dedupe by item_id."""
    all_items: list[dict] = []
    for name in DIGEST_PIPELINES:
        items = fetch_pipeline_items(name)
        for it in items:
            it["_pipeline"] = name
            all_items.append(it)

    seen_ids: set[str] = set()
    unique: list[dict] = []
    for it in all_items:
        iid = item_id(it.get("title", ""), it.get("link", ""))
        if iid not in seen_ids:
            seen_ids.add(iid)
            unique.append(it)
    return unique


def main() -> None:
    parser = argparse.ArgumentParser(description="BirdsAiView — Fetch news for OpenClaw")
    parser.add_argument("--fetch-only", action="store_true", help="Output items as JSON to stdout")
    parser.add_argument("--pipeline", metavar="NAME", help="Fetch single pipeline only")
    args = parser.parse_args()

    if not args.fetch_only:
        print("Usage: python main.py --fetch-only [--pipeline NAME]")
        print("  Outputs JSON for OpenClaw to consume.")
        sys.exit(1)

    if args.pipeline:
        items = fetch_pipeline_items(args.pipeline)
        for it in items:
            it["_pipeline"] = args.pipeline
    else:
        items = fetch_all()

    out = [{"title": it.get("title"), "link": it.get("link"), "summary": it.get("summary"), "source": it.get("source"), "published": it.get("published"), "pipeline": it.get("_pipeline", "")} for it in items]
    print(json.dumps({"items": out}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
