"""
Job Scout skill — fetch job/industry sources, filter by keywords.
Outputs JSON for OpenClaw to consume. No Telegram send.
"""
import os
import sys
import json
import hashlib

# Run from repo root so core and pipelines are importable
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from core.scraper import fetch_sources
from core.deduplicator import deduplicate_semantic


def load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def is_relevant(item: dict, keywords: list[str]) -> bool:
    """Keyword-based relevance."""
    text = _norm(item.get("title", "") + " " + item.get("summary", ""))
    return any(_norm(kw) in text for kw in keywords if (kw or "").strip())


def item_id(title: str, link: str) -> str:
    raw = f"{_norm(title)}|{_norm(link)}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def main() -> None:
    os.chdir(_REPO_ROOT)

    config = load_json("config.json")

    for name in ("job_scout", "jobs"):
        path = os.path.join("pipelines", f"{name}.json")
        if os.path.isfile(path):
            pipeline = load_json(path)
            break
    else:
        pipeline = {
            "sources": [],
            "keywords": ["job", "career", "hiring", "role", "position"],
            "max_items": 10,
        }

    sources = pipeline.get("sources", [])
    keywords = pipeline.get("keywords", [])
    max_items = int(pipeline.get("max_items", 10))

    state_path = os.path.join("state", "seen_job_scout.json")
    seen = set(load_json(state_path)) if os.path.exists(state_path) else set()

    all_items = fetch_sources(sources) if sources else []
    relevant = [it for it in all_items if is_relevant(it, keywords)]
    fresh = []
    for it in relevant:
        iid = item_id(it.get("title", ""), it.get("link", ""))
        if iid not in seen:
            fresh.append(it)
            seen.add(iid)

    fresh = deduplicate_semantic(fresh)
    top = fresh[:max_items]

    os.makedirs(os.path.dirname(state_path), exist_ok=True)
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False, indent=2)

    # Output JSON for OpenClaw
    print(json.dumps({"items": top}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
