"""
Scraper: RSS, NewsAPI, and Playwright-based fetching for news and job postings.
Used by pipelines and OpenClaw skills to pull content from feeds and dynamic sites.
All outputs normalized to: title, summary, link, source, published.
"""
import os
import json
import feedparser
from typing import Any


def _normalize_item(title: str, summary: str, link: str, source: str, published: Any = None) -> dict[str, Any]:
    """Normalize to common schema."""
    return {
        "title": (title or "").strip(),
        "summary": (summary or "").strip(),
        "link": (link or "").strip(),
        "source": source,
        "published": published,
    }


def fetch_rss(urls: list[str]) -> list[dict[str, Any]]:
    """
    Fetch and normalize entries from one or more RSS/Atom feeds.
    Returns list of dicts: title, summary, link, source (feed url), published (optional).
    """
    items: list[dict[str, Any]] = []
    headers = {"User-Agent": "BirdsAiView/1.0 (news digest; +https://github.com)"}
    for url in urls:
        try:
            feed = feedparser.parse(url, request_headers=headers)
            for entry in feed.entries:
                items.append(_normalize_item(
                    entry.get("title"),
                    entry.get("summary"),
                    entry.get("link"),
                    url,
                    entry.get("published"),
                ))
        except Exception:
            pass
    return items


def fetch_newsapi(
    query: str,
    country: str = "my",
    api_key: str | None = None,
    page_size: int = 20,
) -> list[dict[str, Any]]:
    """
    Fetch from NewsAPI (free tier: 100 req/day). Requires NEWSAPI_KEY in env or config.
    Returns normalized items. country='my' for Malaysia.
    """
    key = api_key or os.getenv("NEWSAPI_KEY")
    if not key:
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                key = json.load(f).get("newsapi_key")
        except Exception:
            pass
    if not key:
        return []

    try:
        import requests
        r = requests.get(
            "https://newsapi.org/v2/top-headlines",
            params={"q": query, "country": country, "pageSize": page_size, "apiKey": key},
            timeout=15,
        )
        r.raise_for_status()
        data = r.json()
        items = []
        for art in data.get("articles", []):
            items.append(_normalize_item(
                art.get("title"),
                art.get("description") or "",
                art.get("url") or "",
                art.get("source", {}).get("name", "newsapi"),
                art.get("publishedAt"),
            ))
        return items
    except Exception:
        return []


def fetch_playwright(
    url: str,
    selector: str | None = "article a[href], .post a[href], .news-item a[href]",
) -> list[dict[str, Any]]:
    """
    Playwright-based scraping for dynamic pages without RSS.
    Extracts article links and titles. Requires: pip install playwright && playwright install chromium.

    Usage:
        items = fetch_playwright("https://theedgemalaysia.com", selector="article a")
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return []

    sel = selector or "a[href]"
    items: list[dict[str, Any]] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
            els = page.query_selector_all(sel)
            seen_links = set()
            for el in els:
                try:
                    href = el.get_attribute("href")
                    if not href or href.startswith("#") or href in seen_links:
                        continue
                    if not href.startswith("http"):
                        from urllib.parse import urljoin
                        href = urljoin(url, href)
                    text = (el.inner_text() or "").strip()
                    if len(text) < 10 or len(text) > 200:
                        continue
                    seen_links.add(href)
                    items.append(_normalize_item(text, "", href, url, None))
                except Exception:
                    continue
            browser.close()
    except Exception:
        pass
    return items[:50]


def fetch_sources(sources: list[str] | list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Fetch from mixed sources: URL string = RSS, or {"type":"rss","url":"..."},
    {"type":"newsapi","q":"..."}, {"type":"playwright","url":"...","selector":"..."}.
    """
    items: list[dict[str, Any]] = []
    for s in sources:
        if isinstance(s, str):
            items.extend(fetch_rss([s]))
        elif isinstance(s, dict):
            t = (s.get("type") or "rss").lower()
            if t == "rss":
                u = s.get("url")
                if u:
                    items.extend(fetch_rss([u]))
            elif t == "newsapi":
                q = s.get("q", "Malaysia")
                items.extend(fetch_newsapi(query=q, country=s.get("country", "my")))
            elif t == "playwright":
                u = s.get("url")
                if u:
                    items.extend(fetch_playwright(u, s.get("selector")))
    return items
