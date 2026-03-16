"""
Processor: AI summarization, relevance, quality scoring, impact scoring, and event classification.
Uses OpenAI to filter and summarize so only relevant news is sent.
"""
import os
import json
import re
from datetime import datetime, timezone
from html import unescape
from typing import Any

EVENT_TYPES = ("inflation", "ma", "dev_project", "tech_announcement", "property", "job", "other")
IMPACT_LEVELS = ("Low", "Medium", "High")

# Priority sources get +3, tier-1 +2
PRIORITY_SOURCES = ("bnm.gov", "bank negara", "gov.my", "dosm")
TIER1_SOURCES = ("thestar", "edge", "malaymail", "techinasia", "digitalnewsasia")

def clean_text(s: str) -> str:
    """Strip HTML, OREF labels, normalize whitespace. From InsightsPanel pattern."""
    if not s:
        return ""
    s = re.sub(r"ALERT\[\w+\]:\s*", "", s)
    s = re.sub(r"AREAS\[\w+\]:\s*", "", s)
    s = unescape(s)
    s = re.sub(r"<[^>]+>", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _norm(s: str) -> str:
    return " ".join((clean_text(s or "").strip().lower().split()))


# Optional OpenAI; fail gracefully if not configured
def _get_client():
    try:
        from openai import OpenAI
        key = os.getenv("OPENAI_API_KEY") or _config_key()
        if key:
            return OpenAI(api_key=key)
    except Exception:
        pass
    return None


def _get_llm_model(model: str = "gpt-4o-mini") -> str:
    return os.getenv("OPENAI_MODEL", model)


def _config_key() -> str | None:
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f).get("openai_api_key")
    except Exception:
        return None


def _parse_published(published: Any) -> datetime | None:
    """Parse RSS published date to datetime. Returns None if unparseable."""
    if not published:
        return None
    try:
        from dateutil import parser as dateutil_parser
        dt = dateutil_parser.parse(str(published))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ImportError:
        return None
    except Exception:
        return None


def compute_quality_score(item: dict[str, Any]) -> float:
    """
    Quality score: base(1) + priority_bonus(0-3) + recency(0-2).
    Priority: BNM/official +3, tier-1 +2. Recency: last 6h +2, last 24h +1.
    """
    score = 1.0
    source = (item.get("source") or "").lower()
    for p in PRIORITY_SOURCES:
        if p in source:
            score += 3
            break
    else:
        for t in TIER1_SOURCES:
            if t in source:
                score += 2
                break

    dt = _parse_published(item.get("published"))
    if dt:
        now = datetime.now(timezone.utc)
        age_h = (now - dt).total_seconds() / 3600
        if age_h <= 6:
            score += 2
        elif age_h <= 24:
            score += 1

    item["quality_score"] = score
    return score


def classify_event(item: dict[str, Any]) -> str:
    """Keyword heuristic for event type (Tier 1, no API)."""
    text = _norm(item.get("title", "") + " " + item.get("summary", ""))
    if any(k in text for k in ("inflation", "cpi", "opr", "interest rate", "bnm", "rate cut", "rate hike")):
        return "inflation"
    if any(k in text for k in ("acquire", "acquisition", "merger", "bought", "takeover", "m&a")):
        return "ma"
    if any(k in text for k in ("launch", "develop", "project", "lrt", "mrt", "construction", "development")):
        return "dev_project"
    if any(k in text for k in ("e-invoicing", "software", "fintech", "digital", "tech", "api", "platform")):
        return "tech_announcement"
    if any(k in text for k in ("property", "housing", "mortgage", "rental", "napic", "jpph")):
        return "property"
    if any(k in text for k in ("job", "career", "hiring", "role", "position", "vacancy")):
        return "job"
    return "other"


def classify_events_batch(items: list[dict[str, Any]], model: str = "gpt-4o-mini") -> list[dict[str, Any]]:
    """
    Classify event type for each item. Uses single LLM call for batch when available.
    Mutates items with event_type. Falls back to keyword heuristic if no API.
    """
    client = _get_client()
    if not client or len(items) == 0:
        for it in items:
            it["event_type"] = classify_event(it)
        return items

    # Single batch call
    batch_text = "\n\n".join(
        f"[{i+1}] {it.get('title','')} | {it.get('summary','')[:200]}"
        for i, it in enumerate(items)
    )
    prompt = f"""Classify each item as exactly one of: inflation, ma, dev_project, tech_announcement, property, job, other.
Return a JSON array of strings, one per line number, e.g. ["inflation","ma","other"].
Items:
{batch_text}"""

    try:
        r = client.chat.completions.create(
            model=_get_llm_model(model),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        content = (r.choices[0].message.content or "").strip()
        m = re.search(r"\[[\s\S]*?\]", content)
        arr = json.loads(m.group()) if m else []
        for i, it in enumerate(items):
            et = arr[i] if i < len(arr) and arr[i] in EVENT_TYPES else classify_event(it)
            it["event_type"] = et
    except Exception:
        for it in items:
            it["event_type"] = classify_event(it)
    return items


def score_impact_batch(items: list[dict[str, Any]], model: str = "gpt-4o-mini") -> list[dict[str, Any]]:
    """
    Rate impact Low/Medium/High (12-24 month horizon) per item. Mutates items with impact.
    Uses batch LLM call when available.
    """
    client = _get_client()
    if not client or len(items) == 0:
        for it in items:
            it["impact"] = "Medium"  # Default when no API
        return items

    batch_text = "\n\n".join(
        f"[{i+1}] {it.get('title','')} | {it.get('summary','')[:200]}"
        for i, it in enumerate(items)
    )
    prompt = f"""Rate impact for each item on 12-24 month horizon. Return exactly: Low, Medium, or High.
Be skeptical. PR/hype = Low. Policy changes, M&A, major projects = High.
Return a JSON array of strings, e.g. ["High","Low","Medium"].
Items:
{batch_text}"""

    try:
        r = client.chat.completions.create(
            model=_get_llm_model(model),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=200,
        )
        content = (r.choices[0].message.content or "").strip()
        m = re.search(r"\[[\s\S]*?\]", content)
        arr = json.loads(m.group()) if m else []
        for i, it in enumerate(items):
            imp = arr[i] if i < len(arr) and arr[i] in IMPACT_LEVELS else "Medium"
            it["impact"] = imp
    except Exception:
        for it in items:
            it["impact"] = "Medium"
    return items


def sort_by_impact(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort by quality_score * impact_weight. High=3, Medium=2, Low=1."""
    imp_map = {"High": 3, "Medium": 2, "Low": 1}

    def key(it):
        q = float(it.get("quality_score", 1))
        imp = imp_map.get(it.get("impact", "Medium"), 2)
        return q * imp

    return sorted(items, key=key, reverse=True)


def select_with_source_diversity(
    items: list[dict[str, Any]],
    max_count: int,
    max_per_source: int = 3,
) -> list[dict[str, Any]]:
    """
    Select top items by impact score with source diversity. From InsightsPanel pattern.
    Prevents one source from dominating (max_per_source per source).
    """
    sorted_items = sort_by_impact(items)
    selected: list[dict[str, Any]] = []
    source_count: dict[str, int] = {}
    for it in sorted_items:
        src = (it.get("source") or "unknown").lower()
        if source_count.get(src, 0) < max_per_source:
            selected.append(it)
            source_count[src] = source_count.get(src, 0) + 1
        if len(selected) >= max_count:
            break
    return selected


def select_with_source_diversity(
    items: list[dict[str, Any]],
    max_count: int = 8,
    max_per_source: int = 3,
) -> list[dict[str, Any]]:
    """
    Select top items by impact score with source diversity (InsightsPanel pattern).
    Limits items per source so one feed does not dominate.
    """
    if not items or max_count <= 0:
        return []
    sorted_items = sort_by_impact(items)
    selected: list[dict[str, Any]] = []
    source_count: dict[str, int] = {}
    for it in sorted_items:
        src = (it.get("source") or "").lower()[:80]  # use prefix as source key
        c = source_count.get(src, 0)
        if c < max_per_source:
            selected.append(it)
            source_count[src] = c + 1
        if len(selected) >= max_count:
            break
    return selected


def is_relevant(item: dict[str, Any], keywords: list[str]) -> bool:
    """Keyword-based relevance (no API). Use when AI is not available."""
    text = _norm(item.get("title", "") + " " + item.get("summary", ""))
    return any(_norm(kw) in text for kw in keywords if (kw or "").strip())


def summarize_item(item: dict[str, Any], model: str = "gpt-4o-mini") -> str:
    """
    One-line summary of a single item using the configured LLM.
    Returns original title if API is not available.
    """
    client = _get_client()
    if not client:
        return item.get("title", "") or "No title"
    text = f"Title: {item.get('title', '')}\nSummary: {item.get('summary', '')}"
    try:
        r = client.chat.completions.create(
            model=_get_llm_model(model),
            messages=[{"role": "user", "content": f"Summarize in one short line for a news digest:\n{text}"}],
            max_tokens=80,
        )
        return (r.choices[0].message.content or item.get("title", "")).strip()
    except Exception:
        return item.get("title", "") or "No title"


def summarize_digest_brief(items: list[dict[str, Any]], model: str = "gpt-4o-mini") -> str:
    """
    Generate 2-3 sentence brief of top headlines (InsightsPanel pattern).
    Returns empty string if no API.
    """
    client = _get_client()
    if not client or not items:
        return ""
    titles = [it.get("title", "") or it.get("summary", "")[:80] for it in items[:8]]
    combined = ". ".join(t[:80] for t in titles[:5] if t)
    if not combined:
        return ""
    prompt = f"Summarize the most important headlines in 2-3 concise sentences (under 80 words): {combined}"
    try:
        r = client.chat.completions.create(
            model=_get_llm_model(model),
            messages=[{"role": "user", "content": prompt}],
            max_tokens=150,
        )
        return (r.choices[0].message.content or "").strip()
    except Exception:
        return ""


def summarize_batch(items: list[dict[str, Any]], model: str = "gpt-4o-mini") -> list[dict[str, Any]]:
    """
    Add a short 'summary_line' to each item. Mutates and returns items.
    Skips API calls if OpenAI is not configured.
    """
    client = _get_client()
    if not client:
        for it in items:
            it["summary_line"] = it.get("title", "") or "No title"
        return items
    for it in items:
        it["summary_line"] = summarize_item(it, model=model)
    return items
