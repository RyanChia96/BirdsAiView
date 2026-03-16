"""
Enricher: Optional OpenClaw Web Researcher integration for high-impact items.
When impact is High and event_type is ma or tech_announcement, optionally
call OpenClaw to research and verify. Attach enrichment before summarization.
"""
import os
import json
from typing import Any


def _get_gateway_config() -> tuple[str | None, str | None]:
    """Return (gateway_url, token) from config or env."""
    try:
        with open("config.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
        url = cfg.get("openclaw_gateway_url") or os.getenv("OPENCLAW_GATEWAY_URL", "http://127.0.0.1:18789")
        token = cfg.get("openclaw_gateway_token") or os.getenv("OPENCLAW_GATEWAY_TOKEN")
        return url.rstrip("/"), token
    except Exception:
        return None, None


def enrich_item(item: dict[str, Any]) -> dict[str, Any]:
    """
    If item is high-impact ma/tech_announcement and OpenClaw is configured,
    call Web Researcher and attach enrichment. Returns item (mutated).
    """
    if item.get("impact") != "High":
        return item
    et = item.get("event_type", "")
    if et not in ("ma", "tech_announcement"):
        return item

    url, token = _get_gateway_config()
    if not token:
        return item

    title = item.get("title", "")
    summary = item.get("summary", "")
    prompt = f"Research and verify: {title}. Key facts: {summary[:500]}. Return: confirmed entities, related companies, timeline."

    try:
        import requests
        r = requests.post(
            f"{url}/tools/invoke",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json={
                "tool": "web_researcher",
                "args": {"query": prompt},
            },
            timeout=60,
        )
        if r.status_code == 200:
            data = r.json()
            item["enrichment"] = data.get("result") or data.get("content") or str(data)
    except Exception:
        pass

    return item


def enrich_batch(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Enrich high-impact ma/tech items. Mutates and returns items."""
    for it in items:
        enrich_item(it)
    return items
