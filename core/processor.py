"""
Processor: AI summarization and relevance logic for scraped items.
Uses OpenAI (or Anthropic) to filter and summarize so only relevant news is sent.
"""
import os
import json
from typing import Any

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

def _config_key() -> str | None:
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            return json.load(f).get("openai_api_key")
    except Exception:
        return None


def _norm(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


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
            model=os.getenv("OPENAI_MODEL", model),
            messages=[{"role": "user", "content": f"Summarize in one short line for a news digest:\n{text}"}],
            max_tokens=80,
        )
        return (r.choices[0].message.content or item.get("title", "")).strip()
    except Exception:
        return item.get("title", "") or "No title"


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
